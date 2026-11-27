# 좌표계 및 단위

- 오른손 좌표계, +Z 위. 내부 m/rad/s/kg, 화면 mm/degree.
- 열벡터 p_parent = T_parent_child @ p_child. 합성 T_world_tool =
  T_world_base @ T_base_flange(q) @ T_flange_tool.
- URDF joint: T_parent_child(q) = T_origin(xyz,rpy) @ T_motion(axis,q).
- URDF rpy는 고정축 roll X, pitch Y, yaw Z이며 Rz(yaw) @ Ry(pitch) @ Rx(roll).
  SciPy Rotation.from_euler('xyz', ...)를 사용한다.
- quaternion 저장 순서 (x,y,z,w), 길이 1. q와 -q는 같은 자세다.
- Euler는 표시/입력 전용이며 특이점에서 유일하지 않다. 내부는 행렬을 사용한다.
- base_link, flange, tool0를 구분한다. Generic world/base는 초기 단위 변환이다.
- Mesh 좌표는 링크 visual origin 및 mesh scale을 먼저 적용하고 FK 링크 변환을 적용한다.
- 제조사 좌표 규약·영점·회전 순서는 미확인이다. Generic의 규약을 S922에 적용하지 않는다.
- S922 CAD profile은 별도 CAD 상대각 규약이다. CAD mm/Y-up → 앱 m/Z-up:
  `(x,y,z) → (x,-z,y)/1000`. 원래 STEP 조립 자세가 상대각 0이며 제조사 영점이 아니다.
- CAD에서 추출한 축 방향의 부호는 좌표상 가장 큰 성분이 양수가 되도록 정한 기하학 규약이다.
  실제 제어기의 양의 방향과 일치한다고 판단하지 않는다.
- CAD 플랜지 TCP는 장착 평면/끝단 회전축 교점과 바깥쪽 법선으로 구성한다.
  X/Y twist는 CAD 규약이고 제어기 flange/tool 기준과 미대조 상태다.
