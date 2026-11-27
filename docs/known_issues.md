# 알려진 문제와 미검증 항목

- HITBOT S922 공식 CAD 외형/회전 직선은 적용했다. 제어기 영점/양의 방향/보정은 미확인이다.
  CAD 기준 상대각 ±180°는 제어기 소프트웨어 한계가 아니다. docs/s922_cad.md 참조.
- Phase 3은 IK/충돌 검사를 제공한다. 경로/작업/동역학/LLM/장비 코드 출력은 미구현이다.
- Generic 모델은 장비 사양·도달성·안전성 판단에 사용할 수 없다.
- OpenGL 지원 Windows 데스크톱이 GUI/VTK 검증에 필요하다. 원격/가상 GPU는 별도 검증한다.
- PyBullet cp312/win_amd64 wheel 검색이 실패했다. 소스 빌드 등은 Phase 3 전에 검토한다.
- 시뮬레이션은 현장 안전 검증을 대체하지 않는다. 실제 연결/구동은 구현 범위 밖이다.
- URDF: fixed/revolute/continuous/prismatic tree를 지원한다. mimic/floating/planar,
  xacro, DTD/entity, 원격 mesh는 오류로 거부한다. STL/OBJ 및 명시적 package 매핑만 지원한다.
- URDF inertial/dynamics/transmission은 Phase 1에서 사용하지 않는다.
- mesh당 100MB/200만 삼각형 제한. GUI는 package://를 자동 추정하지 않는다.
- 관절/Base/TCP 변경은 .rsai에 저장한다. 로봇 모델 전환은 객체를 유지하고 Undo 이력을 초기화한다.
- 사용자 객체 mesh만 프로젝트에 내장한다. S922 CAD/외부 URDF와 profile은 다른 PC에 별도 준비한다.
- OBJ 재질/텍스처는 가져오지 않는다. mm/m은 사용자가 지정하며 geometry-only STL로 정규화한다.
- 최대 1,000개 객체, 100단계 계층, 100개 Undo snapshot이다. 대규모 장면/GPU 성능은 미검증이다.
- 충돌 대상은 실제 FCL 검사에 반영한다. 고정/질량/작업 대상은 후속 기능용 메타데이터다.
- 메시 충돌은 conservative convex hull이다. 구멍/오목 영역이 막혀 과검출할 수 있다.
  S922 collision 누락은 incomplete다. 명시적으로 CAD visual 근사를 켠 경우에도 미보정 모델이다.
- 이웃 링크/같은 강체/부착 host는 자동 제외하고 그 쌍을 report에 기록한다. 허용 쌍은 사용자 설정이다.
- 구간은 관절 선형 보간과 보수적 이동량 envelope다. native CCD나 실제 장비 안전 인증이 아니다.
  최대 25,000 part 쌍, 기본 3,000 sample이다. 초과/엔진 오류/형상 누락은 통과하지 않는다.
- IK는 다중 초기값의 local optimizer다. 실패가 도달 불가를 증명하지 않는다. 특이점 진단은
  0.25m 특성 길이로 가중한 6D Jacobian의 rank이며 실제 속도/힘 가동성 보장이 아니다.
- continuous 조그 창은 ±180°이다. 실제 다회전 관절 운전/제어기 의미는 미지원이다.
- 독립 exe는 현재 PC에서만 확인한다. 다른 GPU/Windows 환경은 검증하지 않았다.
- Windows GUI CI는 workflow_dispatch 전용이다. 자동 CI는 핵심 모듈을 검사한다.
- 제조사 CAD/메시는 로컬 전용이다. 저장소 clone/wheel에는 포함하지 않으며 변환 도구로 준비한다.
- S922 collision geometry, 속도/가속도/effort, 질량/관성은 지정하지 않았다.
- S922 표시용 삼각화 설정은 0.35mm/0.22rad이다. STL 정점 재조립 오차 검사(1µm)는
  해석 CAD 곡면에 대한 정밀도/충돌 정확도 보장이 아니다.
