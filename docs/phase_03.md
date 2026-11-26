# Phase 3 기구학과 충돌 검사

2026-11-27 사용자 승인. 작업 브랜치는 feature/phase-03-kinematics-collision이다.
기존 공용 Python 3.12.10을 유지하고 다른 로봇 앱 코드는 사용하지 않는다.
Phase 4 경로 계획/실제 장비 구동은 포함하지 않는다.

## 작업 구분
1. Task 3.1: geometric Jacobian, SO(3) 자세 오차, 관절 한계 내 수치 IK, 특이점 진단.
2. Task 3.2: FCL 자기/환경/부착물 충돌·최소 거리, 허용 쌍, 중간 구간 검사.
3. Task 3.3: 목표 TCP/IK/충돌/구간 검사 GUI와 결과 무효화·시각화.
4. Task 3.4: 통합 회귀, Windows/wheel, 문서/Git/CI/v0.3.0.

## Task 3.1 구현·검증
- TreeKinematics.jacobian은 World의 [TCP 선속도; 각속도] 6×N 행렬이다.
  선택 Tool의 조상 관절만 기여하며 fixed/branch/prismatic/TCP 오프셋을 처리한다.
- BoundedIK는 SciPy trust-region reflective least squares의 관절 한계를 사용한다.
  위치 잔차와 SO(3) log 잔차를 사용하고 log의 inverse right Jacobian으로 미분한다.
  결정적인 다중 초기값, 기본 최대 8회×160 평가, 위치 10µm/회전 0.1mrad 허용치다.
  회전 잔차는 0.25m 특성 길이로 가중하고 최종 위치/회전 오차는 각각 확인한다.
- continuous 관절은 초기값에 가까운 동등각으로 반환한다. 실패는 no_solution_found이며
  도달 불가의 증명이 아니다. accept callback으로 수렴한 후보를 추가 제약으로 거부할 수 있다.
- 특이점은 각속도 행에 선언한 길이를 곱한 SVD/rank로 진단한다. 6D task rank가 6 미만이면
  특이/부족 자유도로 표시한다. 실제 장비의 가동성·속도·특이점 회피 보장이 아니다.
- 실측: IK/Jacobian 및 기존 로봇 테스트 **36 passed (2.37s)**.
  20개 임의 자세 Jacobian 중앙 차분, 큰 회전 오차 미분, 15개 목표의 Base/TCP 합성 IK,
  특이 초기값/π 회전/한계/실패/후보 거부, branch/prismatic, 로컬 S922 포함.

## 충돌 엔진 호환성 결정
이 PC에서 pip의 cp312/win_amd64 바이너리 탐색은 PyBullet과 Coal 모두 실패했다.
python-fcl 0.7.0.11의 공식 Windows wheel은 설치/구체 거리 계산을 통과했다.
wheel metadata가 요구하는 Cython 3.3.2만 추가했고 pip check를 통과했다.
FCL을 교체 가능한 충돌 경계로 사용하고 PyBullet 동역학/재생은 이후 검토한다.

S922는 검증된 collision geometry가 없으므로 무조건 검사 완료로 간주하지 않는다.
명시적으로 선택한 CAD 외형 convex hull 근사는 미보정 근사로 보고할 예정이다.

공식 참고:
- [SciPy bounded least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
- [python-fcl 배포](https://pypi.org/project/python-fcl/)
- [python-fcl 형상/거리 API](https://github.com/BerkeleyAutomation/python-fcl)
- [PyBullet 배포](https://pypi.org/project/pybullet/)
