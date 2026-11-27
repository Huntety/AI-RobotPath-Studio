# Phase 0/1 작업 보고 (2026-11-25)

## 1. 현재 개발 상태
- Phase 0 완료: 기반/아키텍처/규약/데이터 계약/테스트/CI/개발 규칙.
- Phase 1: Task 1.1 모델/FK, Task 1.2 GUI, Task 1.3 최종 번들 검증 완료.
- 사용자 지정 Python/test/RobotStudioAI에서 기존 공용 Python 3.12.14를 사용한다.
- 기존 로봇 앱의 코드/자료를 재사용하지 않은 신규 구현이다.
- Phase 2 이후는 사용자 확인 후 진행한다.

## 2. 구현 내용
- 자체 Generic 6축 URDF, 분리된 visual/collision geometry, 출처/합성 모델 표시.
- fixed/revolute/continuous/prismatic tree 로더, 관절/단위/축/위상/형상 유효성 검사.
- FK와 World/Base/Tool/TCP 변환, immutable Pydantic 경계 데이터.
- PySide6/VTK 메인 GUI, 6관절 슬라이더/수치 입력, 제한, Home/제로, 링크 선택.
- TCP mm/RPY/quaternion/행렬 표시, Tool 링크/오프셋 입력, 좌표축 표시/숨김.
- 비동기 URDF/STL/OBJ 로딩, 오류 시 기존 모델 유지. 실제 장비 통신 기능 없음.
- 카메라 맞춤 시 PyVista가 floor 기준으로 다시 초기화하는 회귀를 수정했다.
- UTF-8 URDF만 허용하여 인코딩에 따른 DTD/entity 필터 우회를 방지했다.

## 3. 변경 파일
새 프로젝트 범위만 변경했다. 기존 test 프로젝트 파일은 수정/삭제하지 않았다.
- 진입점/설정: main.py, start_robotstudio.cmd, pyproject.toml, requirements*.txt.
- src/robotstudio_ai/core/: schema, transforms, robot_model, urdf, kinematics.
- src/robotstudio_ai/gui/: main_window, joint_panel, viewport.
- src/robotstudio_ai/: app, settings, data/config/app.yaml, data/robots/generic_6axis/robot.urdf.
- tests/: foundation, robot_model, gui.
- 배포/CI: RobotStudioAI.spec, build_windows.ps1, tools/verify_wheel.py,
  tools/verify_bundle.py, .github/workflows/tests.yml.
- README, AGENTS, CHANGELOG 및 docs 문서.
- 삭제: 에이전트가 이번 작업에서 만든 별도 .venv만 제거. 사용자 공용 환경 유지.

## 4. 핵심 설계 및 알고리즘
- RobotModel/KinematicsSolver Protocol로 제조사/로더/수치 backend 경계를 분리했다.
- FK: T_world_base × joint(origin × axis motion) 누적 × T_tool_offset.
- 하나의 FKResult를 VTK actor 행렬과 TCP에 적용해 모델/표시 불일치를 방지한다.
- 내부 m/rad, GUI mm/degree, quaternion xyzw, URDF 고정축 xyz 규약.
- RRT/IK/충돌/작업/LLM/제조사 변환은 이번 단계에서 구현했다고 표시하지 않는다.
- 긴 URDF/mesh 로딩은 QThreadPool로 분리한다.
- wheel 자원 검증 및 onedir 번들의 Python PATH 없는 외부 cwd 실행 검사를 제공한다.

## 5. 테스트 및 검증 결과
- 전체 pytest: 43 passed / 11.26s (36 core + 7 GUI), Ruff 및 pip check 통과.
- FK: 해석적 4자세, seed 922의 임의 100자세를 독립 expm 기준과 2e-12 오차로 비교.
- base/tool 합성, 분기/직동/연속/고정 관절, 제한/잘못된 XML/형상/mesh 참조 검사.
- 실제 GUI: slider/spin/keyboard, FK-actor 일치, 제한/상태 보존, TCP 이동/회전,
  좌표축, 비동기 로드 실패 복구, 실제 STL/OBJ 및 screenshot/렌더 픽셀 확인.
- 1000 FK: 총 0.201744s, 평균 0.202ms (이 PC/단일 측정, 성능 보장 아님).
- wheel 0.1.0: source 경로를 제외한 임시 폴더에서 URDF/YAML 및 FK 로드 성공.
- 첫 Windows 번들: venv/Python PATH를 제거한 외부 cwd에서 GUI smoke 성공, actor 10개.
- 최종 0.1.0 번들: 재빌드 후 Python PATH 없는 외부 cwd GUI smoke 통과. version 0.1.0,
  actor 10개, vtkGenericOpenGLRenderWindow. 다른 PC/GPU, 실제 S922 및 현장 검증 미실행.
- 로컬 onedir: 1,715 files, 593,645,445 bytes (약 566 MiB).
- EXE SHA256: `9DF41544AA1A0845E6FA47584820FDE9FAA3127E8C1742436AD08B743442364A`.
- 로그/XML/이미지는 로컬 artifacts/에 보관하며 Git에는 포함하지 않는다.

## 6. Git 및 GitHub
- origin: https://github.com/Huntety/AI-RobotPath-Studio.git
- 브랜치: feature/phase-01-robot-model. 기존 main 초기 Commit e694bb0을 보존했다.
- Phase 0: 7a9f68d `chore(project): initialize RobotStudio AI foundation`,
  Push 및 v0.0.1 tag dereferenced SHA 원격 일치 확인.
- 환경 전환: f522153 `chore(env): use requested Python test shared environment`, Push 확인.
- Task 1.1: 17a897c `feat(robot): add synthetic URDF model and validated forward kinematics`,
  Push 및 원격 SHA 일치 확인.
- Task 1.2: a47b30f `feat(gui): add VTK robot viewer and validated joint controls`,
  Push 및 원격 SHA 일치 확인.
- [PR #2](https://github.com/Huntety/AI-RobotPath-Studio/pull/2) 확인. 기존 열린 PR을 중복 생성하지 않는다.
- a47b30f의 Actions run 45518935366: core success, GUI는 수동 실행 조건으로 skipped.
- Task 1.3 릴리스: v0.1.0. 최종 Commit은 `build(windows): package and verify Phase 1 workbench`.
  자기 자신의 Commit SHA를 문서에 포함할 수 없으므로 정확한 값은 Git 이력/tag 및
  세션 최종 완료 보고를 기준으로 한다. 최종 원격 refs/CI도 완료 보고와 GitHub에서 확인한다.
- main/develop 병합은 수행하지 않았다. 저장소 보호/승인 규칙을 우회하지 않는다.

## 7. 현재 한계 및 알려진 문제
- S922 축/영점/보정/제한/TCP/제어기 사양 미확인. Generic 결과를 S922로 사용하지 않는다.
- IK/Jacobian/충돌/경로/동역학/LLM/작업/실제 코드 출력은 미구현.
- PyBullet cp312 Windows wheel 확인 실패. 후속 Phase 전에 소스 빌드/배포 조합 검토 필요.
- URDF mimic/floating/planar/xacro 및 원격 mesh 미지원; GUI package:// 자동 매핑 미지원.
- mesh당 100MB/200만 삼각형 제한, TCP 변경 세션 전용, 장면 저장/Undo는 Phase 2.
- Windows 번들은 exe와 _internal 폴더를 함께 유지한다. 다른 PC 검증은 수행하지 않았다.

## 8. 프로그램 실행 방법
`start_robotstudio.cmd` 더블클릭 또는 프로젝트 폴더에서:
```powershell
..\Scripts\python.exe main.py
..\Scripts\python.exe main.py --headless-check
..\Scripts\python.exe -m pytest
```
독립 실행: `dist/RobotStudioAI/RobotStudioAI.exe`.
Home/슬라이더를 조작하고 TCP와 링크가 함께 변하는지 확인한다.
설치/빌드/입력 규약은 user_manual.md와 environment.md를 참조한다.

## 9. 다음 개발 작업
Phase 2 Task 2.1: Scene Manager 및 revision, 객체 ID/형상/좌표/상태 계약.
이후 primitive/STL/OBJ 객체 편집, 저장/불러오기, Undo/Redo를 단계적으로 추가한다.
Phase 3 전에 S922의 검증 가능한 자료 및 PyBullet 호환성 문제를 우선 해결한다.
다음 Phase는 사용자 확인 없이 시작하지 않는다.
