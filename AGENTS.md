# RobotStudio AI 개발 규칙

## 목적과 범위
자연어 작업 명세 → 자세 후보 → IK → 충돌 검사 → 관절 공간 경로 → 시간 궤적 →
시뮬레이션 → 제조사 변환 → 제어기 경로 재검증 → 코드 출력의 OLP 플랫폼이다.
Windows/Python 3.12, PySide6, PyVista/VTK를 기본으로 한다. ROS는 필수가 아니다.
사용자 지정 작업 경로는 Python/test/RobotStudioAI이며 상위 공용 가상환경
`../Scripts/python.exe` (Python 3.12.14)를 사용한다. 추가 가상환경을 만들지 않는다.
공용 환경의 기존 패키지는 불필요하게 변경하지 않는다.
사용자 요청: 기존 robot_path_desktop, robot_path_studio 및 HITBOT 웹 스튜디오의 코드를
재사용하지 않고 완전히 새로 구현한다. 기존 프로젝트는 수정하지 않는다.
현재 요청은 Phase 0 및 Phase 1까지다. Phase 2 진행 전에 사용자 확인을 받는다.
실제 로봇 접속·구동 기능을 구현하지 않는다.

## 세션 시작
AGENTS.md, README.md, docs/development_status.md, docs/architecture.md,
docs/known_issues.md를 읽고 git status, 현재 브랜치, 최근 이력과 기존 테스트 결과를 확인한다.
기존 구현을 재사용하고 사용자 변경사항을 보존한다.

## 설계와 정확성
- GUI와 핵심 계산을 분리하고 실제 필요한 인터페이스부터 구현한다.
- RobotModel, KinematicsSolver와 추후 CollisionChecker, MotionPlanner,
  TrajectoryPlanner, GraspPlanner, TaskPlanner, SimulationEngine, LLMProvider,
  PostProcessor는 교체 가능한 경계를 유지한다. 빈 구현을 완료 기능처럼 만들지 않는다.
- 내부 m/rad/s/kg, quaternion xyzw, 열벡터 T_parent_child 규약을 지킨다.
- LLM은 작업 명세만 만들며 좌표·관절·경로·실행 코드를 직접 생성하지 않는다.
- 제조사 사양과 명령을 추정하지 않는다. Generic 모델은 S922와 명확히 구분한다.
- 미검증 경로는 실행 코드로 출력하지 않는다. 장면·모델·TCP 변경은 이전 검증을 무효화한다.
- 타입, docstring, 예외 처리와 logging을 사용한다. 긴 계산은 GUI 스레드 밖에서 처리한다.

## 작업 완료 절차 (매 세션 지속 적용)
설계 → 구현 → 관련 단위/통합/회귀 테스트 → 수정·재검증 → 문서 갱신 → diff 검토 →
민감정보 점검 → Git Commit → GitHub Push → 원격 SHA 확인 → 보고.
각 독립 Task 완료 시 자동 Commit 및 Push한다. Phase 종료까지 미루지 않는다.
README, CHANGELOG, docs/development_status.md와 관련 설계·알려진 문제를 갱신한다.
실패 테스트나 미구현 기능을 완료로 보고하지 않는다. 빈 Commit을 만들지 않는다.
사용자와 무관한 기존 변경사항을 stage/commit하지 않는다.

## Git 및 보안
- origin: https://github.com/Huntety/AI-RobotPath-Studio.git
- feature/*, fix/*, refactor/*, docs/*에서 작업하고 Conventional Commits를 사용한다.
- main은 검증된 상태만 반영한다. develop은 통합용이다. 보호/승인 규칙을 우회하지 않는다.
- Phase 0 v0.0.1, Phase 1 v0.1.0, 이후 v0.2.0 … v0.9.0,
  MVP 검증 완료 v1.0.0. 완료 Phase의 tag도 Push 후 원격 확인한다.
- 사용자 승인 없는 force push, hard reset, 이력 재작성, 브랜치/tag 삭제를 금지한다.
- API key, token, .env, 인증서, venv/cache/log, 대용량 생성물,
  권한 미확인 SDK/CAD/매뉴얼 및 회사·고객 장면을 업로드하지 않는다.
- 인증·네트워크 등 외부 제약 시 로컬 Commit을 보존하고 업로드 상태를 별도 보고한다.
- 새 저장소 생성·권한 변경·실제 제어·데이터 손실 작업은 사용자 확인이 필요하다.

## 보고
현재 Phase/Task, 완료·미완료, 구현 내용, 변경 파일, 설계, 실제 테스트·성능,
브랜치/SHA/메시지/Push/원격/tag/CI, 한계, 실행법, 다음 작업을 보고한다.
