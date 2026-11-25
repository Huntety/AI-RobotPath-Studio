# 알려진 문제와 미검증 항목

- HITBOT S922 공식 CAD 외형/회전 직선은 적용했다. 제어기 영점/양의 방향/보정은 미확인이다.
  CAD 기준 상대각 ±180°는 제어기 소프트웨어 한계가 아니다. docs/s922_cad.md 참조.
- Phase 0/1은 충돌/IK/경로/작업/동역학/LLM/장비 코드 출력이 없는 개발 단계다.
- Generic 모델은 장비 사양·도달성·안전성 판단에 사용할 수 없다.
- OpenGL 지원 Windows 데스크톱이 GUI/VTK 검증에 필요하다. 원격/가상 GPU는 별도 검증한다.
- PyBullet cp312/win_amd64 wheel 검색이 실패했다. 소스 빌드 등은 Phase 3 전에 검토한다.
- 시뮬레이션은 현장 안전 검증을 대체하지 않는다. 실제 연결/구동은 구현 범위 밖이다.
- URDF: fixed/revolute/continuous/prismatic tree를 지원한다. mimic/floating/planar,
  xacro, DTD/entity, 원격 mesh는 오류로 거부한다. STL/OBJ 및 명시적 package 매핑만 지원한다.
- URDF inertial/dynamics/transmission은 Phase 1에서 사용하지 않는다.
- mesh당 100MB/200만 삼각형 제한. GUI는 package://를 자동 추정하지 않는다.
- TCP GUI 변경은 세션에만 유지된다. 장면 저장/Undo/Redo는 Phase 2 범위이다.
- continuous 조그 창은 ±180°이다. 실제 다회전 관절 운전/제어기 의미는 미지원이다.
- 독립 exe는 현재 PC에서만 확인한다. 다른 GPU/Windows 환경은 검증하지 않았다.
- Windows GUI CI는 workflow_dispatch 전용이다. 자동 CI는 핵심 모듈을 검사한다.
- 제조사 CAD/메시는 로컬 전용이다. 저장소 clone/wheel에는 포함하지 않으며 변환 도구로 준비한다.
- S922 collision geometry, 속도/가속도/effort, 질량/관성은 지정하지 않았다.
- S922 표시용 삼각화 설정은 0.35mm/0.22rad이다. STL 정점 재조립 오차 검사(1µm)는
  해석 CAD 곡면에 대한 정밀도/충돌 정확도 보장이 아니다.
