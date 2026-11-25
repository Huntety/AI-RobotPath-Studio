# RobotStudio AI

Windows용 산업용 로봇 오프라인 프로그래밍 플랫폼. 자연어 작업 계획부터 기구학,
충돌 회피, 시뮬레이션, 검증된 제조사 코드 출력까지 단계적으로 개발한다.
Phase 0 완료, Phase 1의 URDF/FK와 GUI를 **Generic 6축 테스트 모델**로 검증했다.
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

## 문서
- [개발 상태](docs/development_status.md)
- [사용법](docs/user_manual.md), [환경 검증](docs/environment.md)
- [아키텍처](docs/architecture.md), [좌표계](docs/coordinate_conventions.md)
- [로봇 사양](docs/robot_specification.md), [알려진 문제](docs/known_issues.md)
- [로드맵](docs/roadmap.md), [에이전트 규칙](AGENTS.md)

개별 Task 완료 시 테스트·문서 갱신·Commit·Push·원격 SHA 확인을 수행한다.
Phase 2 이상은 Phase 1 결과 보고 후 사용자 확인을 받아 진행한다.
