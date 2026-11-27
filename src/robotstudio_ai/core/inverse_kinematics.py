"""Bounded multi-start pose IK and dimensionally scaled Jacobian diagnostics."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from pydantic import Field
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from robotstudio_ai.core.kinematics import IDENTITY_POSE, TreeKinematics
from robotstudio_ai.core.robot_model import RobotModel
from robotstudio_ai.core.schema import Finite, Pose, Record
from robotstudio_ai.core.transforms import pose_matrix


class IKOptions(Record):
    position_tolerance_m: Finite = Field(default=1e-5, gt=0, le=0.01)
    orientation_tolerance_rad: Finite = Field(default=1e-4, gt=0, le=0.1)
    orientation_length_m: Finite = Field(default=0.25, gt=0)
    max_evaluations: int = Field(default=160, ge=1, le=2000)
    attempts: int = Field(default=8, ge=1, le=64)
    random_seed: int = Field(default=922, ge=0)


DEFAULT_IK_OPTIONS = IKOptions()


@dataclass(frozen=True)
class JacobianDiagnostics:
    rank: int
    singular_values: tuple[float, ...]
    condition: float
    singular: bool
    orientation_length_m: float


def diagnose_jacobian(jacobian, orientation_length_m=0.25) -> JacobianDiagnostics:
    """Scale angular rows by a declared length; rank refers to a full 6D TCP task."""
    matrix = np.array(jacobian, dtype=float, copy=True)
    if matrix.ndim != 2 or matrix.shape[0] != 6 or not np.isfinite(matrix).all():
        raise ValueError("Expected a finite 6 by N Jacobian")
    if not np.isfinite(orientation_length_m) or orientation_length_m <= 0:
        raise ValueError("Orientation length must be positive")
    matrix[3:] *= orientation_length_m
    values = np.linalg.svd(matrix, compute_uv=False)
    threshold = max(1e-8, (values[0] if len(values) else 0) * 1e-5)
    rank = int(np.count_nonzero(values > threshold))
    condition = float(values[0] / values[-1]) if rank == 6 else float("inf")
    return JacobianDiagnostics(rank, tuple(values), condition, rank < 6, orientation_length_m)


@dataclass(frozen=True)
class IKResult:
    success: bool
    positions: tuple[float, ...]
    position_error_m: float
    orientation_error_rad: float
    evaluations: int
    attempts: int
    reason: str
    diagnostics: JacobianDiagnostics


def pose_residual(target, actual):
    """World translation error and spatial SO(3) log error, in m/rad."""
    return np.r_[
        target[:3, 3] - actual[:3, 3],
        Rotation.from_matrix(target[:3, :3] @ actual[:3, :3].T).as_rotvec(),
    ]


def residual_jacobian(residual, geometric):
    """Derivative of Log(R_target R_actual.T) using the inverse right Jacobian."""
    x, y, z = residual[3:]
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    angle = np.linalg.norm(residual[3:])
    coefficient = (
        1 / 12 + angle**2 / 720 if angle < 1e-4 else (1 - angle / 2 / np.tan(angle / 2)) / angle**2
    )
    result = -np.array(geometric, copy=True)
    result[3:] = -(np.eye(3) + skew / 2 + coefficient * skew @ skew) @ geometric[3:]
    return result


class BoundedIK:
    """Trust-region reflective least squares; failures never prove unreachability.

    Position and rotation tolerances are checked independently after optimisation.
    Optional candidate filtering can reject poses for collision constraints.
    """

    def solve(
        self,
        model: RobotModel,
        target: Pose,
        seed: Sequence[float],
        tool_link: str,
        base: Pose = IDENTITY_POSE,
        tool_offset: Pose = IDENTITY_POSE,
        options: IKOptions = DEFAULT_IK_OPTIONS,
        accept: Callable[[tuple[float, ...]], bool] | None = None,
    ) -> IKResult:
        initial = np.array(model.validate_positions(seed))
        desired = pose_matrix(Pose.model_validate(target.model_dump()))
        solver = TreeKinematics()
        lower = np.array([j.lower if j.lower is not None else -np.inf for j in model.active_joints])
        upper = np.array([j.upper if j.upper is not None else np.inf for j in model.active_joints])
        free = upper > lower
        rng = np.random.default_rng(options.random_seed)
        weights = np.array([1, 1, 1, *([options.orientation_length_m] * 3)])
        best, best_error, total, blocked = initial.copy(), float("inf"), 0, False
        attempts = 0
        for attempts in range(1, options.attempts + 1):
            start = initial.copy()
            if attempts > 1:
                lo = np.where(np.isfinite(lower), lower, initial - np.pi)
                hi = np.where(np.isfinite(upper), upper, initial + np.pi)
                start = rng.uniform(lo, hi)

            def expand(values):
                q = initial.copy()
                q[free] = values
                return q

            def error(values):
                return pose_residual(
                    desired, solver.forward(model, expand(values), tool_link, base, tool_offset).tcp
                )

            def derivative(values):
                q = expand(values)
                geometric = solver.jacobian(model, q, tool_link, base, tool_offset)
                return weights[:, None] * residual_jacobian(error(values), geometric)[:, free]

            if np.any(free):
                solution = least_squares(
                    lambda values: weights * error(values),
                    start[free],
                    jac=derivative,
                    bounds=(lower[free], upper[free]),
                    method="trf",
                    max_nfev=options.max_evaluations,
                    ftol=1e-12,
                    xtol=1e-12,
                    gtol=1e-12,
                )
                q = expand(solution.x)
                total += solution.nfev
            else:
                q = initial.copy()
                total += 1
            # Choose equivalent continuous angles nearest the requested seed.
            for i, joint in enumerate(model.active_joints):
                if joint.kind == "continuous":
                    q[i] = initial[i] + (q[i] - initial[i] + np.pi) % (2 * np.pi) - np.pi
            model.validate_positions(q)
            residual = pose_residual(
                desired, solver.forward(model, q, tool_link, base, tool_offset).tcp
            )
            position_error, orientation_error = (
                np.linalg.norm(residual[:3]),
                np.linalg.norm(residual[3:]),
            )
            cost = np.linalg.norm(weights * residual)
            if cost < best_error:
                best, best_error = q.copy(), cost
            if (
                position_error <= options.position_tolerance_m
                and orientation_error <= options.orientation_tolerance_rad
            ):
                if accept is None or accept(tuple(q)):
                    return self._result(
                        True,
                        q,
                        residual,
                        total,
                        attempts,
                        "converged",
                        solver,
                        model,
                        tool_link,
                        base,
                        tool_offset,
                        options,
                    )
                blocked = True
            if not np.any(free):
                break
        residual = pose_residual(
            desired, solver.forward(model, best, tool_link, base, tool_offset).tcp
        )
        return self._result(
            False,
            best,
            residual,
            total,
            attempts,
            "candidates_rejected" if blocked else "no_solution_found",
            solver,
            model,
            tool_link,
            base,
            tool_offset,
            options,
        )

    @staticmethod
    def _result(
        success,
        q,
        residual,
        total,
        attempts,
        reason,
        solver,
        model,
        tool_link,
        base,
        tool_offset,
        options,
    ):
        return IKResult(
            success,
            tuple(float(v) for v in q),
            float(np.linalg.norm(residual[:3])),
            float(np.linalg.norm(residual[3:])),
            total,
            attempts,
            reason,
            diagnose_jacobian(
                solver.jacobian(model, q, tool_link, base, tool_offset),
                options.orientation_length_m,
            ),
        )
