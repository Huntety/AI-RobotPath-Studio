# Changelog

## 0.1.0 — Phase 1 (2026-11-25)
- 사용자 지정 Python/test 작업 폴더와 기존 Python 3.12.14 공용 가상환경으로 전환.
- Task 1.1: 자체 Generic URDF, 엄격한 트리/제한/geometry 검증, FK/모델 인터페이스.
- 35 tests 통과, 독립 expm/해석 기준과 FK 비교. 기존 프로젝트 코드는 재사용하지 않음.
- Task 1.2: PySide6/VTK GUI, 관절 수동 조작, TCP/좌표축, 비동기 URDF/mesh 로드.
- GUI 테스트 7개/누적 42개, 실제 렌더 확인. 카메라 맞춤 회귀 수정.
- Task 1.3: Windows onedir 및 wheel 빌드/외부 cwd 검사, 리소스/metadata 포함.
- UTF-8 XML 검증 강화. 최종 누적 43 tests/Ruff/pip check 통과.
- 현재 공용 환경 유지, 무관한 패키지를 lock/배포에서 제외. S922 실모델은 미지원.
- 최종 Windows 0.1.0 번들을 Python PATH 없는 외부 cwd에서 실행/3D/관절/FK 검사 통과.
- wheel 0.1.0의 별도 폴더 자원 로딩/FK 검사 통과. Phase 2는 사용자 확인 대기.

## 0.0.1 — Phase 0 (2026-11-25)
- 별도 Python 패키지, 개발 규칙, 좌표계/아키텍처/로드맵.
- 유효성 검사 데이터 계약 및 강체 변환.
- S922 미확인 사양과 Generic 모델 구분.
- 기반 테스트 7개, Ruff 및 pip check 통과. Windows core CI와 수동 GUI CI 구성.
- 실제 설치 버전 lock과 PyBullet cp312 Windows wheel 부재 기록.
