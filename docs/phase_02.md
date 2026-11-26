# Phase 2 작업환경 편집기

2026-11-26 사용자 승인으로 시작했다. Phase 3 충돌/IK/경로 계획은 포함하지 않는다.

## Task 2.1 장면 데이터와 이력
core/scene.py는 UUID, 이름/분류, box/cylinder/sphere/mesh/frame, SI 자세, 부모,
질량, 표시/충돌 대상/고정/작업 대상 플래그, RGBA와 JSON 사용자 속성을 관리한다.
로봇은 모델 참조, 이름 있는 관절 상태, Base/Tool, TCP 링크 및 표시 상태를 저장한다.
부모는 world/robot_base/robot_tool 또는 다른 객체 UUID이며 순환/누락 참조를 거부한다.
최대 1,000개 객체/100단계 계층, Undo/Redo는 기본 100개 snapshot으로 제한한다.
실제 mesh 데이터는 이력에 복제하지 않고 내용 hash 기반 자산을 참조한다.
revision은 Undo/Redo를 포함한 모든 변경에서 증가한다. SceneToken은 입력 식별자이며
충돌/경로 검증 완료를 뜻하지 않는다. 장면 변경 전 token은 다시 유효해지지 않는다.

## Task 2.2 자산과 프로젝트
프로젝트 `.rsai`는 ZIP이며 내부 scene.json 및 assets/<SHA256>.stl을 담는다.
장면 mesh는 내장하지만 제조사 로봇 CAD/사용자 URDF/모델 프로필은 외부 참조다.
따라서 S922 프로젝트를 다른 PC에서 열려면 해당 PC에도 S922 모델 준비가 필요하다.
Generic 참조에는 사용자 설치 절대경로를 저장하지 않는다.

STL/OBJ import는 원본 단위를 mm/m 중 명시한다. 정점을 SI로 변환한 뒤 중심을 분리하고,
객체 초기 자세에 그 중심을 적용해 원래 좌표를 유지한다. 색상/질량/충돌 형상이나 단위를
파일 이름으로 추정하지 않는다. OBJ 재질/텍스처는 제외하고 geometry-only STL로 저장한다.
원본 파일은 변경하지 않는다. 캐시는 내용 hash로 식별하며 손상된 캐시를 덮어쓰지 않는다.

저장은 임시 파일 작성 후 atomic replace다. 실패 시 기존 프로젝트를 보존한다.
로드는 format/Schema/객체 그래프/자산 hash/ZIP 경로/중복·예상 외 entry를 검사한다.
제한: 원본/변환 mesh 각 100MB, 최대 200만 삼각형, 프로젝트 자산 300MB, metadata 5MB.
파일을 임의 경로로 압축 해제하지 않고 검증된 메시만 관리 캐시에 기록한다.
카메라 position/focal_point/view_up도 검사해 보관할 수 있다.

## 현재 검증
- Task 2.1 및 기존 핵심: 67 passed (3.30s).
- Task 2.2 포함 전체 headless 핵심: 80 passed (6.20s), 기존 GUI 8개는 별도 분리.
- 단위/원본 원점, 원본 파일 제거 후 다른 cache에서 복구, hash 변조/원자적 저장,
  잘못된 ZIP·metadata·camera 검사 통과. 중복 entry 테스트에 의도된 ZIP 경고 1개.
- GUI 연결 및 최종 통합/배포 검증은 Task 2.3/2.4에서 수행한다.

## Task 2.3 GUI 편집
gui/workbench.py가 Phase 1 뷰어에 SceneManager를 연결한다. Primitive/좌표계 생성,
STL/OBJ import, 복제/삭제, 계층 Tree의 표시 체크, 종류/크기/질량/플래그/JSON 속성,
부모 기준 위치·자세를 편집할 수 있다. 로봇을 선택하면 Base 자세를 수정한다.
고정 플래그는 이후 시뮬레이션용 상태이며 편집 잠금을 뜻하지 않는다.

3D 클릭은 VTK picking으로 객체를 선택한다. box widget은 평행 이동/회전만 허용하고
크기 조작은 숫자 입력으로 분리한다. 한 drag의 이벤트는 Undo 한 단계로 묶는다.
[VTK box widget API](https://vtk.org/doc/nightly/html/classvtkBoxWidget.html)를 사용한다.
`Esc`로 선택을 해제하고 카메라를 조작할 수 있다. 전체 맞춤은 보이는 객체/로봇 bounds를 사용한다.

작업환경 저장/불러오기와 mesh import는 worker에서 수행한다. 파싱/모델 검증/mesh 준비가
성공한 뒤 화면에 적용한다. 잘못된 프로젝트를 열면 기존 장면/로봇/카메라를 유지한다.
저장되지 않은 변경은 새 장면/열기/종료 전에 저장·버리기·취소를 선택할 수 있다.
로봇 모델을 전환하면 객체는 유지하지만 Undo 이력은 초기화한다. 모델이 다른 q를 되돌리는
오류를 막기 위한 범위 제한이다. 모델 변경도 revision을 증가시킨다.

로봇 source fingerprint에 링크/관절/제한/실제 mesh bytes를 포함한다. 같은 model_id여도
내용이 달라졌으면 저장된 프로젝트를 그대로 복원하지 않는다.

검증: 전체 99 tests + 추가 native 중간 마우스 drag 1 test 통과. 생성/크기/자세/플래그,
복제/삭제/Undo/Redo, 부모/Tool/Base, VTK picker/변환, STL·OBJ 원본 제거 후 프로젝트 복원,
잘못된 파일 보존, 저장 확인 취소, Generic↔S922 및 S922 프로젝트 복원을 실제 Qt/VTK로 확인했다.
