# Phase 1 사용법

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
초기 모델은 자체 제작 Generic 6-Axis SYNTHETIC이다. HITBOT S922 사양이 아니다.
관절 패널의 슬라이더 또는 숫자로 자세를 변경한다. 회전은 degree, 직동은 mm로 표시한다.
제한은 입력 위젯과 핵심 모델 양쪽에서 검사한다. 마우스를 관절 위에 두면 범위를 볼 수 있다.
Home은 설정 자세, 제로 자세는 0을 각 관절 제한 내로 제한한 자세다.

중앙 3D 화면: 마우스 왼쪽 드래그 회전, Shift+드래그 이동, 휠 확대/축소.
화면 맞춤은 로봇 형상에 카메라를 맞춘다. 왼쪽 링크를 선택하면 해당 형상의 모서리가 표시된다.
Base/Tool/TCP 좌표축을 켜고 끌 수 있다. 축은 X 빨강, Y 초록, Z 파랑이다.
Tool과 TCP가 겹치는 초기 설정에서는 축도 겹친다.

오른쪽 아래 TCP 위치는 World 기준 mm, RPY는 고정축 xyz degree, quaternion은 xyzw다.
하단 TCP 변환행렬은 m 단위 T_world_tcp이다. Euler 특이점은 별도 표시한다.
TCP 설정 탭에서 Tool 링크와 링크 기준 위치·회전 오프셋을 조정할 수 있다.
설정은 현재 세션에만 적용한다. 영구 변경은 별도 YAML을 작성하여 `--config`로 지정한다.

## URDF 열기
파일 → URDF 열기 또는 Ctrl+O. 모델/mesh는 별도 작업 스레드에서 불러온다.
잘못된 URDF/mesh를 열면 기존 모델을 유지하고 이유를 표시한다.
외부 모델은 출처 미검증으로 표시하고 제조사 검증을 자동 부여하지 않는다.
fixed/revolute/continuous/prismatic을 지원한다. continuous 조그 표시는 ±180° 창이다.
단일 루트 tree, 유효한 관절 제한/axis가 필요하다. mimic/floating/planar/xacro는 거부한다.
URDF는 UTF-8(선택적 BOM) XML이어야 하며 DTD/entity를 지원하지 않는다.
STL/OBJ는 URDF 상대경로와 mesh scale을 사용한다. GUI의 package:// 자동 추정은 지원하지 않는다.
Python loader에서는 명시적인 package_dirs 매핑을 전달할 수 있다.
mesh당 100MB, 200만 삼각형 제한이 있다. inertial/dynamics는 사용하지 않는다.

## 검증
```powershell
..\Scripts\python.exe -m pytest -m "not gui"
..\Scripts\python.exe -m pytest -m gui
..\Scripts\python.exe main.py --smoke-test --screenshot artifacts\ui.png --report artifacts\smoke.json
```

이 버전은 수동 모델 자세/FK를 확인하는 Phase 1이다. 충돌·경로·동역학·자동 작업·LLM·
제조사 코드 출력 및 실제 장비 연결/구동은 아직 구현하지 않았다.
