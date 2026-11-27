# 배포 의존성

Phase 3 충돌 검사는 python-fcl 0.7.0.11(BSD 3-Clause)의 Windows wheel을 사용한다.
FCL(BSD), libccd(BSD)의 native binary와 해당 wheel의 license/metadata도 배포에 포함한다.
Cython은 wheel metadata 의존성으로 설치하며 기존 GUI/수치 패키지는 변경하지 않는다.

RobotStudio AI의 자체 제작 Generic URDF와 코드만 프로젝트 저장소에 포함한다.
제조사 CAD/SDK/매뉴얼, 기존 회사 프로젝트 소스, 사용자 작업 장면은 포함하지 않는다.

Windows 번들은 Python/PySide6(PySide6/Qt LGPL/GPL 또는 상용 조건), VTK(BSD),
PyVista(MIT), PyVistaQt(MIT), NumPy(BSD), SciPy(BSD), Pydantic(MIT), PyYAML(MIT),
Trimesh(MIT) 및 그 의존성을 사용한다. 실제 설치 배포판의 LICENSE/COPYING/NOTICE와
METADATA를 빌드 시 함께 보관한다. 각 배포판/Qt 플러그인의 조건이 우선한다.
Qt는 교체 가능한 DLL을 유지하는 onedir 형태로 묶으며 exe 단독 복사는 지원하지 않는다.
외부 배포 전 사용 목적에 맞는 각 구성요소의 라이선스 조건을 확인한다.

requirements-lock.txt는 프로젝트 의존성만 기록한다. 공용 환경의 Torch/기존 애플리케이션을
번들에 포함하지 않는다. 빌드 로그와 중간 생성물/EXE는 Git에 업로드하지 않는다.

S922는 사용자 로컬 요청으로 공식 CAD를 다운로드/변환했다. CAD 커널은 변환용
cadquery-ocp-novtk/OpenCascade이며 일반 GUI/EXE의 런타임 의존성이 아니다.
제조사 원본/파생 메시의 공개 재배포 허가는 확인되지 않아 models/를 Git에서 제외한다.
현재 PC의 onedir 빌드는 로컬 models/hitbot_s922를 복사하며 외부 공개 업로드는 하지 않는다.
