# 알려진 문제와 미검증 항목

- HITBOT S922의 정확한 축/영점/보정/제어기 사양은 미확인이다.
- Phase 0/1은 충돌/IK/경로/작업/동역학/LLM/장비 코드 출력이 없는 개발 단계다.
- Generic 모델은 장비 사양·도달성·안전성 판단에 사용할 수 없다.
- OpenGL 지원 Windows 데스크톱이 GUI/VTK 검증에 필요하다. 원격/가상 GPU는 별도 검증한다.
- PyBullet cp312/win_amd64 wheel 검색이 실패했다. 소스 빌드 등은 Phase 3 전에 검토한다.
- 시뮬레이션은 현장 안전 검증을 대체하지 않는다. 실제 연결/구동은 구현 범위 밖이다.
- URDF: fixed/revolute/continuous/prismatic tree를 지원한다. mimic/floating/planar,
  xacro, DTD/entity, 원격 mesh는 오류로 거부한다. STL/OBJ 및 명시적 package 매핑만 지원한다.
- URDF inertial/dynamics/transmission은 Phase 1에서 사용하지 않는다.
