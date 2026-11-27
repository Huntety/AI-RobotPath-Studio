# RobotStudio AI 0.3.0 사용법

## 실행
Python/test/RobotStudioAI/start_robotstudio.cmd를 더블클릭한다.
상위 Python/test 공용 가상환경을 사용하며 별도 활성화는 필요 없다.
독립 실행본은 `dist/RobotStudioAI/RobotStudioAI.exe`이다. `_internal` 폴더를 함께 유지한다.

```powershell
cd "C:\Users\STEC KB\Desktop\260826HDK\Python\test\RobotStudioAI"
..\Scripts\python.exe main.py
..\Scripts\python.exe main.py --headless-check
```

## 로봇 모델 확인
로컬 공식 CAD를 준비한 PC에서는 HITBOT S922가 기본이다. 상단에서 Generic과 전환한다.
S922의 J1_CAD~J6_CAD는 CAD 조립 자세 기준 상대각이며 실제 제어기 영점과 미대조 상태다.
±180°는 미리보기 창이다. 제어기 소프트웨어 한계로 사용하지 않는다.
CAD가 없는 PC는 자체 제작 Generic 6-Axis SYNTHETIC으로 실행된다.
관절 패널의 슬라이더 또는 숫자로 자세를 변경한다. 회전은 degree, 직동은 mm로 표시한다.
제한은 입력 위젯과 핵심 모델 양쪽에서 검사한다. 마우스를 관절 위에 두면 범위를 볼 수 있다.
Home은 설정 자세, 제로 자세는 0을 각 관절 제한 내로 제한한 자세다.

중앙 3D 화면: 마우스 왼쪽 드래그 회전, Shift+드래그 이동, 휠 확대/축소.
화면 맞춤은 보이는 로봇과 작업환경 전체에 카메라를 맞춘다. 왼쪽 링크를 선택하면 모서리가 표시된다.
Base/Tool/TCP 좌표축을 켜고 끌 수 있다. 축은 X 빨강, Y 초록, Z 파랑이다.
Tool과 TCP가 겹치는 초기 설정에서는 축도 겹친다.

오른쪽 아래 TCP 위치는 World 기준 mm, RPY는 고정축 xyz degree, quaternion은 xyzw다.
하단 TCP 변환행렬은 m 단위 T_world_tcp이다. Euler 특이점은 별도 표시한다.
TCP 설정 탭에서 Tool 링크와 링크 기준 위치·회전 오프셋을 조정할 수 있다.
관절/Base/TCP 설정은 작업환경(.rsai) 저장 시 함께 보관한다.

## 작업환경 편집
상단 + 상자/원통/구/좌표계 또는 예제 환경을 누른다. Tree나 3D 화면에서 객체를 선택한다.
오른쪽 객체 속성에서 이름/종류/부모/위치·회전/크기/질량/색/플래그/JSON 속성을 수정한 뒤
하단 변경 적용을 누른다. 위치는 mm, 회전은 degree, 질량은 kg이다.
자세 수치는 선택한 부모 기준이다. 부모를 바꿀 때 입력 자세도 새 부모 기준으로 해석한다.
로봇을 선택하면 Base 자세를 편집한다. Tool 자식은 TCP 변경과 관절 동작을 따라간다.

마우스 이동·회전을 켜면 선택 객체에 VTK 상자가 나타난다. 가운데 버튼 드래그로 이동하고
상자 면을 왼쪽 버튼으로 드래그해 회전한다. 크기는 속성 숫자로 수정한다.
Esc로 선택을 해제하면 카메라를 조작할 수 있다. 복제는 부모 X방향 50mm 떨어진 위치에 생성한다.
삭제는 하위 객체도 함께 제거하며 Ctrl+Z/다시 실행으로 복원한다. 한 drag는 Undo 한 단계다.
Tree 체크는 표시를 바꾼다. 부모를 숨기면 자식도 숨겨진다.
고정/충돌 대상/작업 대상은 후속 기능용 속성이며 물리 검사나 편집 잠금을 수행하지 않는다.

STL/OBJ 가져오기는 원본 단위를 mm 또는 m로 지정한다. 원점 위치를 보존해 SI 메시로 변환한다.
OBJ 재질/텍스처는 포함하지 않는다. 원본 파일을 수정하지 않고 별도 자산 캐시를 만든다.

## 저장과 복원
Ctrl+N 새 작업환경, Ctrl+O 열기, Ctrl+S 저장, Ctrl+Shift+S 다른 이름으로 저장이다.
.rsai는 객체/부모/속성, 로봇 모델 참조/관절/Base/TCP, 카메라, 사용자 객체 메시를 보관한다.
저장 후 원본 STL/OBJ를 지워도 복원할 수 있다. S922 CAD나 외부 URDF/profile은 내장하지 않으므로
다른 PC에도 같은 모델을 준비해야 한다. 모델 형상/관절 정의가 바뀌면 로드를 거부한다.
잘못된 파일 로드는 현재 장면을 유지한다. 새 장면/열기/종료 시 미저장 변경을 확인한다.
로봇 모델 전환은 객체를 유지하지만 Undo 이력은 초기화한다.

## URDF 열기
파일 → URDF 열기 또는 Ctrl+Shift+O. 모델/mesh는 별도 작업 스레드에서 불러온다.
잘못된 URDF/mesh를 열면 기존 모델을 유지하고 이유를 표시한다.
외부 모델은 출처 미검증으로 표시하고 제조사 검증을 자동 부여하지 않는다.
fixed/revolute/continuous/prismatic을 지원한다. continuous 조그 표시는 ±180° 창이다.
단일 루트 tree, 유효한 관절 제한/axis가 필요하다. mimic/floating/planar/xacro는 거부한다.
URDF는 UTF-8(선택적 BOM) XML이어야 하며 DTD/entity를 지원하지 않는다.
STL/OBJ는 URDF 상대경로와 mesh scale을 사용한다. GUI의 package:// 자동 추정은 지원하지 않는다.
Python loader에서는 명시적인 package_dirs 매핑을 전달할 수 있다.
mesh당 100MB, 200만 삼각형 제한이 있다. inertial/dynamics는 사용하지 않는다.

## 검증
## IK / 충돌 탭
오른쪽 탭에서 IK / 충돌을 선택한다. 아래의 검사/허용 쌍 설정은 패널을 스크롤해서 볼 수 있다.
현재 TCP 또는 선택 객체를 누르면 World 목표가 입력된다. 위치 mm/회전 degree를 직접 수정한 뒤
IK 계산을 누른다. 결과의 위치/회전 오차, rank/condition과 충돌 필터 여부를 확인한다.
성공한 후보만 후보 자세 적용으로 화면에 적용할 수 있다. 장면 변경 후에는 다시 계산한다.

충돌·여유거리 통과 후보만 찾기가 기본이다. S922에는 검증된 충돌 형상이 없으므로
검사 설정의 CAD 외형 근사를 명시적으로 켜고 적용하거나, 필터를 끄고 기구학만 계산해야 한다.
필터를 끈 결과는 충돌 미검사다. CAD/메시는 보수적 convex hull 근사이며 과검출할 수 있다.

안전 여유거리와 구간 이동량 간격을 입력하고 검사 설정 적용을 누른다. 현재 자세 검사는
로봇 전체·환경·Tool/Base 부착물을 검사한다. 숨긴 객체도 충돌 검사 대상이면 검사한다.
위반 쌍/거리/침투는 목록에, 형상/접점은 빨간색, 최소 이격 선은 노란색으로 표시한다.
누락된 형상/샘플 예산 초과는 통과가 아니다. 기본 이웃/같은 강체/부착 host 제외 쌍은 tooltip에 보인다.

시작 자세 기억 → 관절 자세 변경 → 기억한 시작→현재 자세 구간 검사 순서로 중간 구간을 검사한다.
관절 공간 선형 보간이며 장애물 회피 경로를 생성하지 않는다. 이동량 상한을 추가한 보수적 검사다.
실패한 샘플의 위치 t와 빨간 윤곽은 현재 화면의 관절 자세와 다를 수 있다.

설계상 허용되는 접촉은 두 대상을 선택하고 허용 쌍 추가로 명시한다. 해당 쌍은 검사에서 제외된다.
예제의 작업대/base 접촉도 자동 허용하지 않는다. 허용 쌍/여유거리/근사/간격은 .rsai에 저장된다.
설정은 Undo/Redo를 지원한다. Phase 2 파일은 새 버전에서 열 수 있으나 새 충돌 설정을 담은
파일은 이전 0.2.0 프로그램에서 열지 않는다.

## 검증
```powershell
..\Scripts\python.exe -m pytest -m "not gui"
..\Scripts\python.exe -m pytest -m gui
..\Scripts\python.exe main.py --smoke-test --screenshot artifacts\ui.png --report artifacts\smoke.json
```

이 버전은 기구학과 형상 충돌을 검사하는 Phase 3다. 경로·동역학·자동 작업·LLM·
제조사 코드 출력 및 실제 장비 연결/구동은 아직 구현하지 않았다.
S922 CAD 변환/출처/재배포 구분은 s922_cad.md를 참조한다.
