# RobotStudio AI

Windows용 산업용 로봇 오프라인 프로그래밍 플랫폼. 자연어 작업 계획부터 기구학,
충돌 회피, 시뮬레이션, 검증된 제조사 코드 출력까지 단계적으로 개발한다.
Phase 0/1: **Generic 6축 테스트 모델**의 URDF/FK 및 Windows GUI를 구현했다.
HITBOT S922의 정확한 사양은 미확인이다. 실제 로봇 연결/구동 기능은 제공하지 않는다.

## 환경과 설치
Windows, Python 3.12, Git. ROS 설치는 필요 없다.
사용자 지정 작업 위치는 `Python/test/RobotStudioAI`이며 기존 상위 공용 환경을 사용한다.

```powershell
..\Scripts\python.exe -m pip install -r requirements.txt
..\Scripts\python.exe -m pytest -m "not gui"
..\Scripts\python.exe -m ruff check .
..\Scripts\python.exe main.py
```

PySide6 + PyVista/VTK + pyvistaqt, NumPy/SciPy, Pydantic, PyYAML, Trimesh를 사용한다.
`start_robotstudio.cmd`를 더블클릭해 실행할 수도 있다.
PyBullet은 충돌/시뮬레이션 Phase에서 연결한다.
현재 핵심 데이터 모듈은 GUI import 없이 테스트할 수 있다.
새 PC는 Python 3.12 가상환경에 같은 requirements를 설치하면 된다.
기존 robot_path_desktop/robot_path_studio 코드를 재사용하지 않는 신규 구현이다.

## 현재 기능
- 검증된 URDF tree 로딩, 관절 제한, visual/collision 형상 분리.
- VTK 3D 뷰, 6관절 슬라이더/수치 조작, Home/제로 자세, 링크 선택.
- World/Base/Tool/TCP 변환, 위치·RPY·quaternion·행렬 표시, TCP 오프셋 입력.
- 비동기 URDF/STL/OBJ 로딩 및 실패 복구. 모든 형상과 TCP에 같은 FK 결과 적용.
- IK·충돌·경로·작업 계획·LLM·제조사 코드 출력은 후속 Phase에 구현한다.

## 독립 Windows 실행 파일
로컬 빌드 결과: `dist/RobotStudioAI/RobotStudioAI.exe`.
`_internal`을 포함한 RobotStudioAI 폴더 전체가 필요하며 exe만 복사하면 실행되지 않는다.
Python 설치 없이 실행하는 onedir 번들이다. 현재 PC에서 확인하며 다른 PC는 별도 검증이 필요하다.

```powershell
..\Scripts\python.exe -m pip install -e ".[bundle]"
.\build_windows.ps1
..\Scripts\python.exe tools\verify_bundle.py
```

소스 배포 wheel:
```powershell
..\Scripts\python.exe -m build --wheel --no-isolation
..\Scripts\python.exe tools\verify_wheel.py
```

빌드 출력·가상환경·회사/제조사 자료는 GitHub에 업로드하지 않는다.

## 문서
- [개발 상태](docs/development_status.md)
- [사용법](docs/user_manual.md), [환경 검증](docs/environment.md)
- [아키텍처](docs/architecture.md), [좌표계](docs/coordinate_conventions.md)
- [로봇 사양](docs/robot_specification.md), [알려진 문제](docs/known_issues.md)
- [로드맵](docs/roadmap.md), [에이전트 규칙](AGENTS.md)
- [Phase 0/1 보고서](docs/phase_01_report.md)

개별 Task 완료 시 테스트·문서 갱신·Commit·Push·원격 SHA 확인을 수행한다.
Phase 2 이상은 Phase 1 결과 보고 후 사용자 확인을 받아 진행한다.
