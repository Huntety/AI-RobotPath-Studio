# Changelog

## Unreleased — Phase 2
- Task 2.2: 내용 hash의 SI mesh 자산, .rsai portable 프로젝트, atomic 저장 및 엄격한 로드 검증.
- STL/OBJ의 mm/m 단위와 원점을 보존하고 원본/제조사 CAD를 임의로 수정하거나 복사하지 않음.
- 핵심 80 tests 통과. 원본 제거 후 복구/잘못된 archive·checksum·camera 검증 포함.
- Task 2.1: 장면/객체/형상/자산/로봇 상태 계약과 원자적 Scene Manager.
- 부모 좌표계, 복제/하위 삭제, bounded Undo/Redo, 단조 revision/token 무효화.
- Scene 및 기존 핵심 계산 테스트 67개 통과. GUI/프로젝트 파일은 후속 Task.

## 0.1.1 — S922 공식 CAD (2026-11-26)
- 공식 STEP V3.0 2024-04-29의 7개 부품/13재질/199,329 삼각형을 로컬 모델로 적용.
- 이웃 원통 면으로 6개 회전 직선 추출, 도면 425/395mm 및 메시 재조립 대조.
- Generic↔S922 전환과 CAD 상대각/영점 미보정 표시. 동역학/충돌 사양을 임의 생성하지 않음.
- hash 고정 다운로드/STEP 변환 도구. CAD 커널은 변환 시만 사용하며 기존 VTK 유지.
- 원본/파생 메시를 Git에서 제외하고 로컬 Windows 번들에만 포함.
- Generic 회귀 포함 60 tests/Ruff/pip check 통과. 실제 제어기 모델 검증은 별도 과제.
- 0.1.1 Windows 번들을 Python 경로 없는 외부 cwd에서 S922/13 actors/관절/FK/VTK 검사 통과.

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
