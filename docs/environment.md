# 개발 환경과 호환성 확인

2026-11-25, 초기 Python 3.12.10 환경에서 설치 후 사용자 요청으로
Python/test 공용 Python 3.12.14 환경으로 전환했다.
기존 NumPy 2.5.2, PySide6 6.11.2, Pillow 12.3.0, packaging 26.3은 유지했다.
프로젝트 실행은 `../Scripts/python.exe`를 사용한다. 처음 만든 자체 .venv는 제거했다.
공용 환경 pip check 및 기존 QtWebEngine import가 통과했다. 아래는 초기 설치 기록이다.

| 구성 | 설치 버전 | 확인 |
|---|---|---|
| NumPy / SciPy | 2.5.5 / 1.18.1 | transform 테스트 통과 |
| Pydantic / PyYAML | 2.14.4 / 6.0.4 | 데이터 검증 통과 / import |
| PySide6 | 6.12.0 | Windows abi3 wheel 설치 |
| PyVista / VTK / pyvistaqt | 0.49.3 / 9.7.2 / 0.14.1 | Windows wheel 설치, GUI는 Phase 1 검증 |
| Trimesh | 5.2.2 | 설치, mesh 로딩은 Phase 1 검증 |
| pytest / pytest-qt / Ruff | 9.2.0 / 4.5.0 / 0.17.6 | 기반 7 tests / lint 통과 |
| PyInstaller | 6.22.3 | 설치, 번들은 Phase 1 검증 |
| PyBullet | 설치 제외 | cp312/win_amd64 wheel 검색 실패 |

`pip download --only-binary=:all: --no-deps pybullet`은 해당 인덱스/플랫폼에서
`No matching distribution found`로 실패했다. 라이브러리 전체가 Python 3.12에서
불가능하다고 단정하지 않는다. 소스 빌드/컴파일러 또는 검증된 배포판 조합을
Phase 3 전에 검토한다. Python 3.12를 변경하지 않았으며 Phase 1은 PyBullet을 쓰지 않는다.

의존성 범위는 pyproject.toml, 실제 설치된 전체 버전은 requirements-lock.txt로 기록한다.
재현: `python -m pip install -r requirements-lock.txt` 다음 `python -m pip install --no-deps -e .`.
lock은 이 Windows 개발 환경 기준이다. CI는 pyproject 범위의 조합도 확인한다.
공용 환경 전환 후 lock은 기존 프로젝트 패키지 목록의 버전만 갱신했다.
Torch/기존 프로젝트를 비롯한 공용 환경의 무관한 패키지는 lock에 넣지 않았다.
GUI는 PySide6 6.11.2/PyVista 0.49.3/VTK 9.7.2/pyvistaqt 0.14.1 조합에서 검증했다.

샌드박스 TEMP 경로의 `{...}`를 setuptools가 변수로 해석하는 오류가 있었다.
이 환경에서 설치/빌드할 때 TEMP와 TMP를 프로젝트 `.cache/tmp` 절대경로로 지정하면 해결된다.
일반 Windows 설치에는 필요하지 않다. 초기 pip DNS 제한은 승인된 네트워크 실행으로 해결했다.

공식 참고:
- [Qt for Python 설치](https://doc.qt.io/qtforpython-6/gettingstarted.html)
- [PyVista 설치](https://docs.pyvista.org/getting-started/installation)
- [PyVistaQt](https://qt.pyvista.org/index.html)
- [PyBullet 공식 Quickstart](https://raw.githubusercontent.com/bulletphysics/bullet3/master/docs/pybullet_quickstartguide.pdf)
