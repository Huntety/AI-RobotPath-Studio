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

## 단계별 검증 이력
- Task 2.1 및 기존 핵심: 67 passed (3.30s).
- Task 2.2 포함 전체 headless 핵심: 80 passed (6.20s), 기존 GUI 8개는 별도 분리.
- 단위/원본 원점, 원본 파일 제거 후 다른 cache에서 복구, hash 변조/원자적 저장,
  잘못된 ZIP·metadata·camera 검사 통과. 중복 entry 테스트에 의도된 ZIP 경고 1개.
- 이후 GUI 연결 및 최종 통합/배포 검증은 아래 Task 2.3/2.4에 기록한다.

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

## Task 2.4 최종 통합·배포 검증 (2026-11-27)
- pytest 전체: **100 passed, 18.180s, failures/errors/skipped 각 0**.
- Ruff check/format 및 pip check 통과. 중복 ZIP 거부 검사의 의도된 경고도 명시적으로 검증했다.
- 소스 GUI smoke: 0.2.0, S922 CAD 상대각/13 actors, 5개 예제 환경 객체.
  관절/FK/actor 행렬 대조, 객체 숫자 편집/Undo/Redo/token 무효화 및
  비동기 .rsai 저장→객체 삭제→복원까지 성공했다. 실제 OpenGL 화면도 확인했다.
- wheel 0.2.0의 별도 폴더 로드/자원/Generic FK 확인 통과. 제조사 CAD는 wheel에 포함하지 않는다.
- Windows 0.2.0 onedir: Python/venv/Qt 경로를 제거한 외부 cwd에서 위와 같은
  S922/5객체/편집/Undo·Redo/프로젝트 복원 smoke 통과. OpenCascade는 번들에 포함하지 않는다.
  배포 폴더 합계 599,959,809 bytes, EXE 24,208,271 bytes.
  EXE SHA256: `3FE8820A5391130C89BC77A83BFAA2D08A8B1DB555054F38041EC3328467D026`.
- 100객체를 100회 계산한 CPU 평균: world transforms 2.019ms, 검증된 편집 5.511ms.
  현재 PC 측정이며 렌더/GPU/파일 처리는 제외한다. 다른 환경의 보장 수치가 아니다.

## 완료 보고
1. **개발 상태**: Phase 2 Task 2.1~2.4 기능 구현과 통합 검증을 완료했다.
   Phase 3 IK/충돌/경로 계획과 실제 장비 구동은 포함하지 않는다.
2. **구현 내용**: 장면/계층/속성, primitive·STL·OBJ, 3D picking/rigid widget,
   Undo/Redo와 변경 무효화, 로봇/Base/TCP/카메라 및 자산 내장 프로젝트를 제공한다.
   카메라 전체 맞춤과 스크롤 밖 변경 적용 버튼, 도움말/메뉴를 정리했다.
3. **변경 파일**: core/scene.py, core/project_io.py, scene_profiles.py,
   gui/scene_view.py, gui/object_editor.py, gui/workbench.py 및 관련 테스트를 생성했다.
   app.py/settings.py/버전/배포 검증 도구와 README·설계·사용법·상태 문서를 수정했다.
   삭제 파일은 없다. 원본 CAD/메시/실행 파일/테스트 산출물은 Git에서 제외한다.
4. **설계**: 검증된 단일 SceneDocument, bounded snapshot 이력, FK 기반 부모 변환,
   단조 revision, 내용 hash 메시, atomic ZIP, 모델 fingerprint와 worker 입출력을 사용한다.
5. **검증**: 위 실측을 참조한다. 실제 S922 제어기 및 다른 PC/GPU의 실행은 미검증이다.
6. **Git**: feature/phase-02-scene-editor. Task 2.1 48512f2, 2.2 bbc04ad,
   2.3 c4a2bb2는 각각 Push/원격 SHA 확인했다. 최종 Task 2.4 SHA는 이 문서를 포함하는
   Commit 및 v0.2.0 tag로 식별한다. 최종 Push/tag/CI는 완료 답변의 확인 결과를 참조한다.
7. **한계**: S922 제어기 영점/방향/한계/관성 미보정, 충돌 geometry 미지정.
   질량/고정/충돌/작업 대상은 메타데이터다. 1,000객체/100계층/100 Undo 제한이 있다.
   OBJ 재질 미지원, 제조사/외부 로봇 모델은 다른 PC에 별도 준비해야 한다.
8. **실행**: 프로젝트에서 `../Scripts/python.exe main.py` 또는 start_robotstudio.cmd.
   독립본은 dist/RobotStudioAI/RobotStudioAI.exe이며 _internal/models를 함께 유지한다.
   예제 환경→객체 속성→Undo/Redo→Ctrl+S/Ctrl+O로 기능을 확인할 수 있다.
9. **다음**: 사용자 승인 후 Phase 3의 수치 IK/Jacobian 및 자기/환경/부착물 충돌과
   edge 검사를 구현한다. 먼저 S922 좌표 보정 자료와 Windows 충돌 엔진 호환성을 확인한다.
