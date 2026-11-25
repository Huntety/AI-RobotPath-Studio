# 아키텍처

## 데이터 흐름
User → Scene Manager → 작업 명세 → Task Planner → Grasp/Work Pose Planner →
Kinematics → Collision Checker → Motion Planner → Trajectory Planner →
Path Validator → Simulation → PostProcessor → Controller Path Validation → Export.
실패한 자세/IK/경로는 후보 선택으로 돌아간다. Phase 1은 URDF → RobotModel → FK →
링크 변환/TCP → Viewport와 수치 표시까지만 구현한다.

## 경계 및 구현 순서
src/robotstudio_ai/core는 GUI import 없이 동작한다. gui는 계산 결과를 소비한다.
RobotModel은 링크/관절/제한/출처를, KinematicsSolver는 관절 상태에서 링크 변환을 제공한다.
충돌/경로/궤적/파지/작업/시뮬레이션/LLM/제조사 변환 인터페이스는 해당 Phase에 실제
입출력이 필요한 시점에 작성한다. 형식적인 미구현 모듈은 생성하지 않는다.

## 주요 데이터 계약
| 데이터 | 내용 | 단위/규약 |
|---|---|---|
| Pose | position_m, quaternion_xyzw | m, 단위 quaternion, 부모에서 본 자식 |
| JointState | names, positions | 이름 순서 명시, 회전 rad/직동 m |
| ModelProvenance | model_id, synthetic, source, hardware_validated | 제조사/가상 모델 구분 |
| Link transform | link name → 4x4 | T_world_link |
| Scene (Phase 2 설계) | UUID, parent, geometry, pose, flags, revision | 렌더/충돌 공통 원본 |
| Path (Phase 4 설계) | ordered JointState, scene/model revision | 시간 없음 |
| Trajectory (Phase 4 설계) | t, q, qdot, qddot | s, SI |
| Validation (향후) | inputs hash/revisions, checks, failures, resolution | 변경 시 무효화 |

## 폴더
src 레이아웃을 사용해 설치된 패키지와 테스트 import를 일치시킨다.
패키지 data/에 자체 제작 URDF와 기본 설정을 포함하여 wheel/Windows 번들에서 경로를 유지한다.
tests/는 계산과 GUI를 구분한다. docs/는 상태·규약·사양·로드맵을 관리한다.
장면 편집, PyBullet, LLM 및 제조사 코드 생성은 이후 Phase로 남긴다.

## 설계 기록
- 2026-11-25: 별도 RobotStudioAI 폴더 및 지정 origin의 초기 이력을 보존한다.
- 사용자 지시에 따라 Python/test/RobotStudioAI로 이동하고 기존 공용 가상환경을 사용한다.
- Generic 모델로 초기 검증한다. 기존 웹 스튜디오의 근사 DH를 제조사 사양으로 재사용하지 않는다.
- PyBullet은 Phase 1 필수 의존성에서 제외한다. 현재는 동역학/충돌을 구현하지 않기 때문이다.
- 사용자의 추가 지시에 따라 기존 로봇 앱 소스는 재사용하지 않고 완전히 신규 작성했다.
- UI 관절 이벤트 → 모델 제한 검사 → TreeKinematics → FKResult 하나 → VTK actor 행렬과
  TCP 표시를 갱신한다. render의 독립 근사 기구학을 만들지 않는다.
- URDF/STL/OBJ 로딩은 QThreadPool에서 수행하고 성공한 모델만 UI에 반영한다.
- Windows onedir는 자체 URDF/YAML과 Qt/VTK DLL을 포함한다. 외부 cwd/Python PATH 없이
  smoke 검증한다. wheel도 소스 경로를 제거한 별도 임시 폴더에서 자원을 확인한다.
- 2026-11-26: 공식 S922 STEP의 7개 부품에서 CAD 참조 모델을 생성한다.
  제어기 영점·동역학 값을 임의로 채우는 URDF 대신 명시적인 CAD manifest를 추가했다.
  기존 RobotModel/KinematicsSolver/FKResult 계약과 tree 자료구조를 그대로 소비한다.
- CAD profile은 외부 models/에 보관한다. source 기본 경로는 프로젝트 models/,
  frozen 기본 경로는 exe 옆 models/다. 없으면 Generic을 사용한다.
- ModelProvenance.joint_coordinates=cad_relative는 미보정 CAD 모델을 구분한다.
  CAD loader는 synthetic/hardware_validated 오표시를 거부한다.
- 모델 전환은 비동기 로드 완료 후 base/tool/home/형상/좌표 표시를 함께 교체한다.
