# RobotStudio AI

**Windows용 산업용 로봇 작업환경 편집기 · 현재 버전 0.2.0 · Phase 2 완료**
최종 갱신: 2026-11-27 (Asia/Seoul)

HITBOT Z-Arm S922를 대상으로 개발하는 오프라인 프로그래밍(OLP) 플랫폼입니다.
현재는 공식 S922 CAD를 표시하고, 관절과 TCP를 조작하며, 로봇 주변의 작업대·공작물·장애물을
구성하고 프로젝트로 저장할 수 있습니다. 자연어 자동 작업, IK, 충돌 회피, 경로 계획과
제조사 코드 생성은 단계별로 추가합니다.

> S922 관절값은 CAD 조립 자세 기준 상대각입니다. 제어기 영점·방향은 미보정이며,
> 실제 로봇 연결·구동 기능은 없습니다.

## 소스와 개발 상태

현재 실행 가능한 소스는 [`feature/phase-02-scene-editor`](https://github.com/Huntety/AI-RobotPath-Studio/tree/feature/phase-02-scene-editor)에 있습니다.
[Phase 2 PR #4](https://github.com/Huntety/AI-RobotPath-Studio/pull/4)는 기존 S922 CAD PR을 잇는 후속 PR입니다.
기본 브랜치 `main`의 이 안내문은 최신 개발 상태를 보여주며, 기능 코드의 병합 상태와 구분합니다.

```powershell
git clone --branch feature/phase-02-scene-editor https://github.com/Huntety/AI-RobotPath-Studio.git
```

| 단계 | 내용 | 상태 |
|---|---|---|
| Phase 0 | 환경·데이터 계약·단위/좌표계·Git/CI | 완료 |
| Phase 1 | URDF·FK·관절/TCP GUI·공식 S922 CAD | 완료 |
| Phase 2 | 작업환경 객체·3D 편집·프로젝트·Undo/Redo | 완료, 0.2.0 |
| Phase 3 | IK·Jacobian·자기/환경/부착물 충돌 | 다음 단계, 사용자 승인 전 |
| Phase 4~6 | 경로·궤적·파지·Pick & Place 시뮬레이션 | 예정 |
| Phase 7~9 | 제조사 변환·LLM 작업 명세·MVP 검증 | 예정 |

## 지금 사용할 수 있는 기능

- **로봇 모델**: 자체 Generic URDF와 공식 HITBOT S922 V3.0 STEP 기반 CAD 모델을 전환합니다.
  S922는 7개 강체/13개 재질이며, 로컬 CAD가 준비된 PC에서는 기본으로 표시합니다.
- **자세와 좌표계**: 6관절 슬라이더/수치 입력, Home/제로 자세, FK, Base/Tool/TCP,
  위치·RPY·quaternion·변환행렬, TCP 오프셋을 제공합니다.
- **작업환경**: 상자·원통·구·좌표계 생성, STL/OBJ 가져오기(mm/m 지정), 객체 종류·크기·질량·색·플래그·JSON 속성을 편집합니다.
- **3D 편집**: Tree/마우스 선택, 이동·회전, 복제·삭제·표시/숨김,
  World/Base/Tool/객체 부모 좌표계를 지원합니다.
- **변경 이력**: Undo/Redo, 한 번의 마우스 drag를 한 단계로 병합,
  장면 변경 revision으로 이전 입력 상태를 무효화합니다.
- **프로젝트**: `.rsai`에 객체/부모/속성/사용자 메시와 로봇 관절/Base/TCP/카메라를 저장합니다.
  원본 STL/OBJ를 삭제해도 내장 자산으로 복원합니다. 큰 파일 처리는 worker에서 수행합니다.

## 실행

Windows와 Python 3.12를 사용하며 ROS 설치는 필요하지 않습니다.
GUI는 PySide6, PyVista/VTK, pyvistaqt를 사용하고 핵심 계산은 NumPy/SciPy/Pydantic으로 분리합니다.
기존 로봇 프로그램의 소스를 재사용하지 않은 신규 구현입니다.

현재 작업 PC에서는 `Python/test/RobotStudioAI`와 기존 상위 공용 가상환경을 사용합니다.
새 가상환경은 만들지 않습니다. 프로젝트 폴더에서 실행하세요.

```powershell
..\Scripts\python.exe -m pip install -r requirements.txt
..\Scripts\python.exe main.py
```

`start_robotstudio.cmd`를 더블클릭해도 됩니다. 다른 PC의 설치는 아래 환경 문서를 참고하세요.

### 빠른 확인 순서

1. 실행 후 S922 또는 Generic 모델의 관절을 움직여 TCP 표시를 확인합니다.
2. **예제 환경**을 누르고 작업대·공작물·장애물을 선택합니다.
3. **객체 속성 → 변경 적용** 또는 마우스 이동·회전으로 편집합니다.
4. **Ctrl+Z / 다시 실행**으로 이력을 확인합니다.
5. **Ctrl+S**로 `.rsai`를 저장하고 **Ctrl+O**로 다시 엽니다.

`Esc`는 선택 해제, 화면 맞춤은 보이는 로봇과 환경 전체를 맞춥니다.
URDF 열기 단축키는 **Ctrl+Shift+O**입니다.

## Windows 독립 실행 파일

로컬 빌드 결과는 `dist/RobotStudioAI/RobotStudioAI.exe`입니다.
Python 설치 없이 실행하는 onedir 배포본이며 `_internal`과 `models`를 포함한
**RobotStudioAI 폴더 전체**를 유지해야 합니다. 실행 파일은 GitHub에 업로드하지 않습니다.

```powershell
..\Scripts\python.exe -m pip install -e ".[bundle]"
.\build_windows.ps1
..\Scripts\python.exe tools\verify_bundle.py
```

wheel 빌드와 검증:

```powershell
..\Scripts\python.exe -m build --wheel --no-isolation
..\Scripts\python.exe tools\verify_wheel.py
```

## S922 CAD 준비

현재 작업 PC에는 준비되어 있습니다. 새 환경에서는 공식 자료를 내려받아 변환합니다.
CAD 변환용 OpenCascade는 선택 의존성이며 GUI 실행 파일에는 포함하지 않습니다.

```powershell
..\Scripts\python.exe -m pip install -e ".[cad]"
..\Scripts\python.exe tools\prepare_s922.py
```

제조사 원본/파생 메시는 재배포 권한이 확인되기 전까지 로컬 `models/`와 `.cache/`에만 보관합니다.
저장소와 wheel에는 포함하지 않습니다. CAD가 없으면 Generic으로 시작합니다.
S922 프로젝트를 다른 PC에서 열려면 같은 로봇 모델을 별도로 준비해야 합니다.

## 검증 결과

2026-11-27 현재 작업 PC에서 확인한 결과입니다.

| 검증 | 결과 |
|---|---|
| pytest 전체 | **100 passed**, 18.180초, 실패/오류/skip 0 |
| 실제 Qt/VTK | picking·마우스 drag·Undo/Redo·S922 전환·저장/복원 통과 |
| 잘못된 프로젝트 | ZIP/그래프/hash/모델 변경 거부 및 기존 장면 보존 통과 |
| Ruff / 패키지 의존성 | check·format·pip check 통과 |
| wheel 0.2.0 | 소스 경로 없는 별도 폴더에서 자원/Generic FK 통과 |
| Windows 0.2.0 | Python PATH 없는 외부 cwd에서 S922/5객체/편집/파일 복원 통과 |
| GitHub Actions | [Windows 핵심 CI 통과](https://github.com/Huntety/AI-RobotPath-Studio/actions/runs/45913055770), GUI CI는 수동 실행 조건 |

100객체/100회 CPU 측정 평균: 부모 변환 계산 2.019ms, 검증된 장면 편집 5.511ms입니다.
렌더링을 제외한 이 PC의 측정값이며 다른 장비의 성능을 보장하지 않습니다.

```powershell
..\Scripts\python.exe -m pytest
..\Scripts\python.exe -m ruff check .
..\Scripts\python.exe main.py --smoke-test --screenshot artifacts\ui.png --report artifacts\smoke.json
```

## 현재 한계

- S922 제어기 영점/양의 방향/실제 관절 한계, 보정·속도·가속도·질량/관성·충돌 형상은 미확정입니다.
  CAD 상대각 ±180°는 실제 제어기 한계가 아닙니다.
- IK·충돌 검사·경로/궤적 계획·동역학·LLM·제조사 코드 출력은 아직 구현하지 않았습니다.
  충돌 대상/고정/질량/작업 대상 플래그는 저장되는 메타데이터입니다.
- 최대 1,000객체/100단계 계층/100 Undo snapshot입니다. OBJ 재질/텍스처는 가져오지 않습니다.
  로봇 모델 전환은 환경 객체를 유지하고 Undo 이력을 초기화합니다.
- 독립 실행 파일은 현재 PC에서 검증했습니다. 다른 Windows/GPU는 별도 확인이 필요합니다.
- 장면/모델 변경 token은 입력 상태 식별자이며 안전 검증 증명서가 아닙니다.

## 문서와 다음 작업

문서 링크는 현재 개발 소스를 가리킵니다.

- [Phase 2 구현·검증 보고](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/phase_02.md)
- [사용법](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/user_manual.md)
- [개발 상태](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/development_status.md) · [로드맵](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/roadmap.md)
- [설계](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/architecture.md) · [좌표 규약](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/coordinate_conventions.md)
- [환경](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/environment.md) · [알려진 문제](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/known_issues.md)
- [S922 CAD 출처·변환·보정 한계](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/docs/s922_cad.md)
- [개발 규칙](https://github.com/Huntety/AI-RobotPath-Studio/blob/feature/phase-02-scene-editor/AGENTS.md)

다음은 사용자 승인 후 Phase 3의 수치 IK/Jacobian과 자기·환경·부착물 충돌 검사입니다.
먼저 S922 좌표 보정 자료와 Windows 충돌 엔진 호환성을 확인합니다.

작업이 끝날 때마다 이 README를 현재 상태로 다시 정리하고, `main`의 README도 즉시 갱신합니다.
기능 코드는 별도 브랜치/PR 절차를 따릅니다. 비밀정보·회사 장면·제조사 CAD·빌드 산출물은 업로드하지 않습니다.
