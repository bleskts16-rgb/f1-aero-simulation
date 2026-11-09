# 설계 목록 CFD: screening (grid2_L1)

- 목록 `data/designs/screening.csv`, 결과 JSON `docs/results/cfd_screening_grid2_L1/<id>.json`, 케이스 `cfd/runs/screening/<id>_grid2_L1`
- 값은 전체 차량(반쪽 ×2), 마지막 1000회 평균 ± 자기상관 보정 표준오차, q = 1500 Pa. CL·A는 다운포스 +.
- Δ는 base 대비. 표면장(평균 Cp, Cf)은 각 케이스의 `surface_fields.npz`에 있다(저장소에는 없음).

| id | 바꾼 값 | 상태 | 셀 [M] | CL·A | CD·A | ΔCL·A | ΔCD·A | 앞날개 CL·A | 뒷날개 CL·A | 시간 [h] |
|---|---|---|---|---|---|---|---|---|---|---|

0/41 완료.
