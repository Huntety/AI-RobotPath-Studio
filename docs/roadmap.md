# 개발 로드맵

| Phase | 범위 | 상태 |
|---|---|---|
| 0 | 환경, 아키텍처, 규약, 데이터 계약, 테스트, Git/CI | 완료, v0.0.1 원격 확인 |
| 1 | Generic URDF, FK, GUI/VTK, 관절/TCP, 통합 검증 | 1.1 검증 완료, 1.2 다음 |
| 2 | 장면 객체/mesh, 편집, 저장, undo/redo, revision | 사용자 확인 후 |
| 3 | IK/Jacobian, 자기/환경/부착물 충돌 및 edge 검사 | 예정 |
| 4 | RRT-Connect, 최적화, 가감속 궤적, 재검증 | 예정 |
| 5 | box/cylinder 파지 후보, 접근·배치, 전체 후보 평가 | 예정 |
| 6 | Pick & Place, 부착/분리, 경로 재생 | 예정 |
| 7 | 검증된 제조사 변환 및 제어기 경로 재검증 | 자료 확보 필요 |
| 8 | LLM 작업 명세/스키마, 수동 입력 경로 | 예정 |
| 9 | 통합·회귀·성능, MVP 검증 | 예정 |
| 10 | NACHI/YASKAWA, 복잡한 파지·비전·동역학 | 향후 |

Phase 1 Task: 1.1 URDF 모델/FK/독립 수치 검증, 1.2 GUI/관절 조작/TCP,
1.3 통합·배포 실행 검증 및 문서. Task별 Commit/Push와 SHA 확인, 완료 시 v0.1.0.
