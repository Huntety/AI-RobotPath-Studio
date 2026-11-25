# 개발 상태

기준일: 2026-11-25 (Asia/Seoul)

- 현재 Phase: 1, Task 1.1 URDF/FK 로컬 검증 완료, Commit/Push 진행.
- 기존 상태: 원격 main의 README 초기 Commit e694bb0을 보존하여 시작.
- 로컬 경로: C:/Users/STEC KB/Desktop/260826HDK/Python/test/RobotStudioAI.
- Python: 사용자 지정 상위 공용 환경 ../Scripts/python.exe (3.12.14).
- 사용자 지시에 따라 프로젝트를 Python/test로 이동했다. 기존 test 파일은 변경하지 않는다.
- 완료: 폴더 구조, SI/좌표 규약, immutable Pydantic 계약, transform, 문서/개발 규칙.
- 완료: 의존성 설치, editable 설치, 테스트/CI 구성, 요구 버전 lock.
- Phase 0 Git: 7a9f68d, feature/phase-00-foundation 및 v0.0.1 Push/원격 SHA 확인 완료.
- 진행: Phase 1. GitHub Actions 결과는 아직 확인 전.
- 완료: 자체 제작 Generic URDF, 시각/충돌 형상 분리, 제한/트리 검사, FK 인터페이스.
- 미완료: Task 1.2 GUI, Task 1.3 패키징 및 통합 검증.
- 실제 테스트 결과: 공용 환경 pytest 35 passed (1.70s), Ruff 및 pip check 통과.
- FK 검증: 해석적 4자세, seed 922의 100개 임의 자세와 독립 expm 기준 비교(2e-12 허용),
  base/tool 합성, 직동/연속/고정/분기 관절, 제한 위반/비정상 URDF/mesh 참조 거부.
- 성능: 이 PC 1000 FK 0.201744s, 평균 0.202ms (보장 수치 아님).
- 다음: Task 1.2 PySide6/PyVista GUI와 관절 조작.
- 문제: S922 검증 사양 없음. Generic 모델을 별도로 사용한다.
- 환경: PyBullet Windows cp312 wheel 없음; Phase 1 필수 의존성에서 제외. docs/environment.md 참조.
- 사용자 지시: 기존 로봇 프로그램 코드를 재사용하지 않고 신규 구현. 공용 환경만 사용.
