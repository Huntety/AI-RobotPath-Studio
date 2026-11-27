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

S922는 검증된 collision geometry가 없으므로 기본 검사는 incomplete이며 clear가 아니다.
CollisionSettings.use_visual_fallback을 명시한 경우에만 CAD 외형을 근사해 검사한다.

## Task 3.2 구현·검증
- CollisionChecker 경계와 worker 전용 FCLSceneChecker가 같은 FK/장면 변환을 사용한다.
  primitive는 native solid이며 메시마다 보수적 convex hull을 만든다. 평면 재질 패치는
  최소 2µm 두께의 enclosing box를 쓴다. 오목 영역/구멍은 막혀 false positive가 날 수 있다.
  메시 hash/크기/삼각형 수, 모델 ID/지문/관절 이름/한계와 scene token을 확인한다.
- 단일 자세 검사는 자기 충돌, 환경, Tool/Base에 연결된 객체와 하위 객체를 포함한다.
  표시 상태와 독립적이며 collision_enabled만 검사 제외에 사용한다.
  정적 환경끼리의 충돌은 관절 자세 검사에서 제외한다. 실제 동역학은 수행하지 않는다.
- 같은 강체/관절 이웃 링크와 부착 host 강체는 자동 제외한다. 제외 쌍을 report에 명시한다.
  allowed_pairs는 별도로 저장하고 잘못된 ID를 거부한다. 객체 삭제 시 관련 쌍도 같은 Undo로 지운다.
- FCL collide 후 분리된 쌍만 unsigned distance를 요청한다. 침투 깊이는 contact에서 별도 기록하고
  intersecting 쌍의 최소 거리는 0으로 보고한다. margin 이하도 위반으로 판정한다.
- 구간 q(t)는 관절 공간 선형 보간이다. 각 관절의 Δq와 전체 체인의 보수적 reach 상한으로
  점 이동량을 제한하고 기본 10mm/0.05rad 이하 간격으로 검사한다.
  각 sample의 margin에 실제 interval 이동량 상한 D를 추가한다. 구간의 임의 점은 가장 가까운
  sample에서 각 형상별 D/2 이내이므로 두 움직이는 형상의 상대 오차는 D 이하다.
  따라서 통과는 표현된 형상에 대한 보수적 envelope 검사이며 native CCD/실제 로봇 인증이 아니다.
  샘플 예산 초과/누락 형상/엔진 오류는 통과가 아니다. 실패 구간은 첫 위반에서 중단한다.
- CollisionSettings는 .rsai에 포함되며 기본 margin 5mm/최대 3,000 sample이다.
  기본 25,000 part pair를 넘는 입력은 거부한다. 대규모 장면은 별도 broadphase 개선이 필요하다.
- 실측: 전체 headless 핵심 **99 passed (7.25s)**, GUI 18개는 이후 통합에서 실행한다.
  구체 해석 거리/회전 Base/숨김·활성 플래그/허용 쌍 저장·삭제·Undo/원본 hash 변조/메시 포함 관계,
  부착물/전체 링크/비이웃 자기 충돌, 양 끝은 clear인 얇은 장애물 구간, 회전 구간,
  sample 예산 초과와 실제 S922 누락/명시적 CAD 근사를 확인했다.

공식 참고:
- [SciPy bounded least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
- [python-fcl 배포](https://pypi.org/project/python-fcl/)
- [python-fcl 형상/거리 API](https://github.com/BerkeleyAutomation/python-fcl)
- [PyBullet 배포](https://pypi.org/project/pybullet/)

## Task 3.3 GUI 구현·검증
- PlanningWorkbench는 Phase 2 편집기를 확장해 IK / 충돌 탭을 제공한다.
  목표는 World mm/degree이며 현재 TCP 또는 선택 객체의 World 자세를 가져올 수 있다.
- IK는 worker에서 계산하고 오차/rank/condition/평가 수/CAD 상대각 여부를 표시한다.
  기본 후보 필터는 충돌/여유거리를 확인한다. 충돌 미검사 모드는 별도 표시한다.
  성공 후보만 적용하며 적용/Undo를 포함한 장면 변경은 이전 분석 결과를 무효화한다.
- 현재 자세 검사와 기억한 q→현재 q 구간 검사를 제공한다. 시작 q는 현재 Base/TCP/장면으로
  다시 검사한다. 모델이 바뀌면 시작 q도 지운다. 경로 생성/시뮬레이션 재생은 구현하지 않는다.
- 충돌/여유 위반 쌍과 거리/침투, 최근접 점, 검사 시점의 빨간 형상 윤곽/접점을 표시한다.
  구간 실패의 윤곽은 현재 q와 다를 수 있으며 샘플 시점이라는 문구를 함께 표시한다.
- 허용 쌍/근사 선택/여유거리/해상도는 프로젝트에 보관하고 Undo로 복구한다.
  계산 중 입력을 잠그며 도중 장면/목표가 바뀐 worker 결과는 버린다.
- 실제 GUI 7 tests 통과: IK 필터/목표 변경/적용/Undo, 전체 링크 접점과 revision 무효화,
  양 끝은 통과하는 중간 구간 위반, 정책/허용 쌍 저장 복원, 지연 worker 결과 폐기,
  부모 객체의 World 목표, S922 누락→명시적 근사.
- 통합 **124 passed (25.19s)**, Ruff/pip check 통과. source GUI smoke도 S922/13 actors/
  5객체/편집·파일 복원/IK 수렴/충돌 complete/구간 complete를 통과했다.
  예제 작업대와 로봇 base의 접촉은 위반으로 표시되며 자동으로 허용하지 않는다.
