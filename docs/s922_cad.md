# HITBOT S922 공식 CAD 적용 (0.1.1)

## 출처와 모델 확인
- [HITBOT 공식 S922 페이지](https://en.hitbot.cc/six-axis-collaborative-robotic-arm/55.html)
- [공식 다운로드 센터](https://www.hitbot.cc/download/)
- [공식 CAD ZIP](https://cn.hitbot.cc/hitbot/product/arm6/z-arms922/z-arms922.zip)
- [공식 치수/운동 범위 도면](https://cn.hitbot.cc/hitbot/product/arm6/z-arms922/z-arms922.pdf)
- [영문 제품 자료](https://en.hitbot.cc/uploads/upload/files/20260803/cbfbdfe90b1467e37742186164201505.pdf)

확인일: 2026-11-26. CAD는 S922 V3.0 2024-04-29, SolidWorks 2022의 STEP AP214다.
새 영문 사이트의 [CAD 링크](https://en.hitbot.cc/uploads/upload/zip/20260613/512f785a629d1b1199d07644d1a5f074.zip)도
다운로드하여 구 다운로드 센터 ZIP과 SHA256이 같음을 확인했다.

- ZIP SHA256: `ab3508233adfdcd933543c8c34df2c04a35d06c8d64bab242a32764062d2cd31`
- STEP SHA256: `3f8a3fe62a90e4fc06cf60ef1a0170a293dd3ced227f30be248abb08b7b8cd09`
- 조립 구조: S922-1 ~ S922-7, 베이스 + 6개 가동 링크.
- 변환 결과: 199,329 triangles, 13개 재질별 STL, 약 10MB.
- 공식 도면의 주요 팔 길이 425/395mm와 CAD 회전축 간 거리를 0.01mm 이내로 대조했다.

원본 CAD 및 변환 메시의 공개 재배포 조건은 확인되지 않았다. 사용자가 요청한 로컬 적용만
수행하며 `.cache/`와 `models/`는 Git에서 제외한다. GitHub에는 변환 도구/검증 코드/출처만
업로드한다. 기존 웹 스튜디오의 소스·DH·메시를 재사용하지 않았다.

## 로컬 준비 및 실행
현재 PC에는 이미 준비되어 있어 기존 실행 방법으로 S922가 기본 표시된다.
상단 모델 선택에서 Generic 6축 검증 모델로 돌아갈 수 있다.

새 환경에서는 프로젝트 폴더에서:
```powershell
..\Scripts\python.exe -m pip install -e ".[cad]"
..\Scripts\python.exe tools\prepare_s922.py
..\Scripts\python.exe main.py
```

다운로드한 ZIP이 있다면 `--zip 경로`를 사용한다. ZIP hash가 변경되거나 부품/축 구조가
예상과 다르면 변환을 중단한다. 기존 출력 폴더는 덮어쓰지 않는다.
기본 결과는 `models/hitbot_s922/`의 app.yaml, model.json, audit.json, meshes/다.
STEP 변환에는 OpenCascade(cadquery-ocp-novtk 7.9.3.1)가 필요하다.
GUI/EXE 실행 시에는 CAD 커널이 필요하지 않고 변환된 메시만 읽는다.
기존 VTK 9.7.2를 변경하지 않기 위해 novtk 빌드를 사용했다.

Windows 빌드는 로컬 `models/hitbot_s922`가 있으면 exe 옆 models/로 복사한다.
모델 폴더 없이 빌드한 배포본과 일반 wheel은 Generic으로 실행된다.
S922 번들을 복사할 때는 exe, _internal, models를 함께 유지한다.

## 적용 방식과 좌표
1. STEP XCAF 조립 계층과 부품 배치, 면 색상을 OpenCascade로 읽는다.
2. 이웃 부품의 일치하는 원통 면으로 공통 회전축을 찾는다. 복수 후보/누락은 거부한다.
3. CAD Y-up를 앱 Z-up로 변환한다: `(x,y,z)_CAD mm → (x,-z,y)_World / 1000`.
4. 축 원점은 해당 회전 직선에서 원점에 가장 가까운 점이다. 베어링 단면 중심을 의미하지
   않으며, 직선 위의 어느 점을 택해도 같은 회전이 되는 기하학적 표현이다.
5. q=0은 배포 STEP의 원래 조립 자세다. 각 링크 메시를 해당 축 원점 기준 SI 좌표로 저장한다.
6. 부품을 면 색상별 STL로 나누고 URDF와 같은 Geometry/RobotModel/FK 인터페이스로 표시한다.
   BRep 삼각화 설정은 선형 편차 0.35mm, 각도 편차 0.22rad이다.
   아래 1µm 재조립 허용치와 float32 오차는 삼각화된 정점의 저장/좌표 변환 검사이며,
   전체 곡면이 해석 CAD와 1µm 이내라는 의미는 아니다. 충돌/정밀 계측용 모델로 검증하지 않았다.
7. 끝단 축과 플랜지 장착 평면의 교점으로 TCP 위치와 법선을 계산한다.
   플랜지 X/Y 회전은 명시적인 CAD 규약이며 제조사 Tool 영점과는 미대조 상태다.

## 실제 제어기 모델과의 구분
**공식 CAD 외형이 적용됐지만, 제어기 좌표와 일치하는 S922 운동학 모델로 검증한 것은 아니다.**

- 화면 J1_CAD ~ J6_CAD는 원래 조립 자세에서의 오른손 상대 회전이다.
- 각 ±180°는 미리보기 범위이며 실제 소프트웨어/기계 한계라는 뜻이 아니다.
- 공식 제품 자료의 제어기 소프트웨어 범위는 별도 audit에 기록한다:
  J1 ±175°, J2 -265°~85°, J3 ±160°, J4 -265°~85°, J5/J6 ±175°.
  영점/회전 방향 대응이 미확인이라 이 값을 CAD 상대각 한계로 혼용하지 않는다.
- 최대 속도/가속도/effort, 질량/관성/payload, 보정값은 임의로 입력하지 않았다.
  CAD 모델의 Joint.velocity는 None이다. 미검증 값을 채우는 URDF 대신 별도 CAD manifest를 쓴다.
- visual 형상을 검증된 collision mesh로 간주하지 않는다. 이 모델은 collision 형상을 갖지 않는다.
- 모델의 metadata는 `synthetic=false`, `hardware_validated=false`, `joint_coordinates=cad_relative`다.
  잘못된 검증/합성 모델 표시는 CAD 로더가 거부한다.
- 화면과 로그/TCP 그룹에 CAD 상대각·영점 미보정을 표시한다. 실제 코드/장비 연결 기능은 없다.

추가 확보 자료: 축별 제어기 영점과 CAD 조립각의 대응, 양의 회전 방향, 플랜지 X/Y 기준,
제조사 FK 기준 자세, 보정/관성/속도/가속도, 충돌 형상 및 재배포 허가.

## 검증과 완료 보고
- 기존 Generic 회귀 + CAD 데이터/경로/축/metadata 검사 + 실제 Qt/VTK: 60 passed (10.83s).
- 실제 S922 메시 전부를 q=0으로 재조립하여 변환 전 삼각화 메시의 부품 경계와 1µm 허용 오차로 비교.
- STL float32 변환 실제 최대 오차는 audit.json에 부품별 기록(전체 최대 약 0.015µm).
- 혼합 6관절 자세를 독립 expm/Rodrigues 회전 직선 기준과 2e-12 오차로 대조.
- 6개 관절 spin 조작, 상위 링크 불변, FK-actor 일치, Generic↔S922 전환을 실제 GUI에서 확인.
- Ruff/pip check 통과. 원본/화면/검증 로그는 로컬 artifacts/ 및 .cache/에 보관한다.
- 본체 외형/관절 조작은 완료했다. 실제 장비·제어기 영점·충돌/동역학·다른 PC 검증은 미실행이다.
- Windows 0.1.1 배포본을 Python/venv 경로를 제거한 외부 cwd에서 실행하여
  S922 선택, 관절/FK/13개 actor/실제 VTK 렌더링과 screenshot 저장을 확인했다.
- EXE SHA256: `C40A473A85B8CC49E1A0F7441847D84E39E8B6C04150A81340AB7E2AC5E4D124`.
- 실행 시 exe/_internal/models를 함께 유지한다. CAD 커널은 배포본에 포함하지 않는다.
- 최종 Git 및 CI 결과는 세션 완료 보고와 Git refs/Actions에서 확인한다.
- 작업 브랜치: feature/s922-official-cad. 최종 Commit 식별자는 해당 브랜치 이력이 원본이다.
- Phase 2 개발은 이번 작업에 포함하지 않는다. 다음은 제어기 기준 좌표 자료 확보 또는 Scene Manager다.

## 작업 완료 보고 (9개 항목)
1. 상태: Phase 1 추가 Task S922-CAD, 외형/관절 조작/모델 전환/로컬 배포 완료.
2. 구현: 공식 STEP 다운로드/검증/변환, CAD manifest 로더, 모델 전환과 미보정 상태 표시.
3. 파일: tools/prepare_s922.py, core/cad_model.py, settings/schema/GUI, 테스트/빌드/문서.
   제조사 원본/메시는 로컬 생성만 수행했으며 기존 프로젝트 파일 삭제 없음.
4. 설계: 공통 원통 면으로 축 추출, SI 변환, CAD 상대각 FK, 제어기 좌표/한계와 분리.
5. 검증: 60 tests/Ruff/pip check, wheel, 독립 Windows 실행 통과. 실패 0.
   실제 로봇/제어기 보정/충돌/동역학/다른 PC 검증은 미실행.
6. Git: feature/s922-official-cad. 최종 Commit 메시지
   `feat(robot): add official S922 CAD reference model workflow`.
   SHA/Push/원격/tag/Actions는 최종 완료 보고와 Git refs가 원본이다. main 병합 없음.
7. 한계: CAD 외형은 공식 자료지만 제어기 영점/방향/회전 범위 대응은 미검증이다.
8. 실행: start_robotstudio.cmd 또는 dist/RobotStudioAI/RobotStudioAI.exe.
   신규 PC는 위 CAD 준비 명령을 실행한다. 이미 준비된 PC에서는 S922가 기본 모델이다.
9. 다음: 영점/회전 방향/FK 기준 자료 대조 또는 사용자 확인 후 Phase 2 Scene Manager.
