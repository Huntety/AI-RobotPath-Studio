# 개발 상태

기준일: 2026-11-25 (Asia/Seoul)

- 현재 Phase: 1 구현/로컬 검증 완료, Task 1.3 최종 릴리스 기록.
- 기존 상태: 원격 main의 README 초기 Commit e694bb0을 보존하여 시작.
- 로컬 경로: C:/Users/STEC KB/Desktop/260826HDK/Python/test/RobotStudioAI.
- Python: 사용자 지정 상위 공용 환경 ../Scripts/python.exe (3.12.14).
- 사용자 지시에 따라 프로젝트를 Python/test로 이동했다. 기존 test 파일은 변경하지 않는다.
- 완료: 폴더 구조, SI/좌표 규약, immutable Pydantic 계약, transform, 문서/개발 규칙.
- 완료: 의존성 설치, editable 설치, 테스트/CI 구성, 요구 버전 lock.
- Phase 0 Git: 7a9f68d, feature/phase-00-foundation 및 v0.0.1 Push/원격 SHA 확인 완료.
- GitHub Actions: a47b30f의 PR run 45518935366 core success. GUI CI는 수동 조건으로 skipped.
- 완료: 자체 제작 Generic URDF, 시각/충돌 형상 분리, 제한/트리 검사, FK 인터페이스.
- Task 1.1: 17a897c Push/원격 SHA 확인 완료.
- Task 1.2: a47b30f Push/원격 SHA 확인 완료.
- 완료: PySide6/VTK GUI, 6관절 슬라이더/수치 입력, 제한, 링크 선택, TCP/좌표축,
  Tool 오프셋, 비동기 URDF/STL/OBJ 로딩, 실패 시 기존 모델 보존.
- 완료: 최종 0.1.0 Windows onedir/wheel 및 독립 실행 검사.
- Phase 1의 기능 구현 미완료 항목 없음 (Generic 검증 범위). S922 실사양은 후속 자료 필요.
- 릴리스: v0.1.0. 최종 Commit 식별자는 Git 이력과 tag를 기준으로 하며,
  최종 Push/tag/CI 확인 결과는 세션 완료 보고 및 GitHub refs/Actions를 참조한다.
- 실제 테스트 결과: 공용 환경 pytest 43 passed (11.26s), Ruff 및 pip check 통과.
- FK 검증: 해석적 4자세, seed 922의 100개 임의 자세와 독립 expm 기준 비교(2e-12 허용),
  base/tool 합성, 직동/연속/고정/분기 관절, 제한 위반/비정상 URDF/mesh 참조 거부.
- 성능: 이 PC 1000 FK 0.201744s, 평균 0.202ms (보장 수치 아님).
- GUI 검증: 7 tests 통과. core 36개와 누적 43 tests. 실제 VTK OpenGL 렌더/스크린샷 확인.
- 배포 검증: wheel 0.1.0을 소스 경로 없는 별도 폴더에서 로딩/FK 확인.
  최종 Windows 0.1.0 번들의 Python PATH 없는 외부 cwd 실행/관절/FK/VTK 검증 통과.
  10 visual actors, vtkGenericOpenGLRenderWindow. 로컬 번들 593,645,445 bytes.
- 카메라 맞춤 회귀를 발견하여 camera_set 처리로 수정 후 GUI 테스트 재통과.
- 다음: Phase 1 결과 보고 후 사용자 확인을 받아 Phase 2 Scene Manager부터 진행한다.
- 문제: S922 검증 사양 없음. Generic 모델을 별도로 사용한다.
- 환경: PyBullet Windows cp312 wheel 없음; Phase 1 필수 의존성에서 제외. docs/environment.md 참조.
- 사용자 지시: 기존 로봇 프로그램 코드를 재사용하지 않고 신규 구현. 공용 환경만 사용.
