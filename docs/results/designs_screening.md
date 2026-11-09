# 설계 목록 빌드 검사: screening

- 목록: `data/designs/screening.csv` (41개), 형상: `cad/out/screening/<id>_half`
- 커밋: c2ec16a (작업 트리 변경 있음)
- 판정: 규정 검사(기준 볼륨, 슬롯, 덮음, 형상 규칙, 바퀴 간극)와 형상 QA(로프트 이탈, 양의 부피, 부착, STL 닫힘)를 모두 통과하면 OK. 계산 실패(ERROR)는 통과가 아니다.

| id | 바꾼 값 | 판정 | 시간 [s] | 실패 항목 |
|---|---|---|---|---|
| base | baseline | OK | 334 | – |
| FW1_lo | FW1=-3 | OK | 344 | – |
| FW1_hi | FW1=3 | NG | 378 | App.1 3.10 front wing in RV-FW-PROFILES/FWEP-*/FW-PYLON: 11.8 cm3 out, max 14 mm at X -725 (XR -4125), Y 291, Z 249 |
| FW2_lo | FW2=-4 | OK | 390 | – |
| FW2_hi | FW2=4 | NG | 378 | App.1 3.10 front wing in RV-FW-PROFILES/FWEP-*/FW-PYLON: 10.6 cm3 out, max 8 mm at X -906 (XR -4306), Y 0, Z 133 |
| FW3_lo | FW3=-3 | OK | 340 | – |
| FW3_hi | FW3=3 | OK | 330 | – |
| FW4_lo | FW4=0.85 | NG | 337 | App.1 3.10 front wing in RV-FW-PROFILES/FWEP-*/FW-PYLON: 0.6 cm3 out, max 1 mm at X -1146 (XR -4546), Y 0, Z 59 |
| FW4_hi | FW4=1.15 | NG | 345 | App.1 3.10 front wing in RV-FW-PROFILES/FWEP-*/FW-PYLON: 0.5 cm3 out, max 3 mm at X -735 (XR -4135), Y 269, Z 229 |
| FW5_lo | FW5=0.04 | OK | 340 | – |
| FW5_hi | FW5=0.08 | NG | 335 | App.1 3.10 front wing in RV-FW-PROFILES/FWEP-*/FW-PYLON: 0.2 cm3 out, max 1 mm at X -1159 (XR -4559), Y 0, Z 59 |
| RW1_lo | RW1=-3 | OK | 362 | – |
| RW1_hi | RW1=1 | OK | 330 | – |
| RW2_lo | RW2=-5 | OK | 360 | – |
| RW2_hi | RW2=1 | OK | 399 | – |
| RW3_lo | RW3=-5 | OK | 425 | – |
| RW3_hi | RW3=15 | NG | 580 | App.1 s25/26 RW Z max [mm]: 883.5713440029155<br>App.1 3.11 rear wing in RV-RW-PROFILES/RWEP-BODY/RW-PYLON/stays: 0.1 cm3 out, max 4 mm at X 3947 (XR 547), Y 552, Z 884 |
| EC1_hi | EC1=30 | OK | 591 | – |
| EC2_lo | EC2=0.85 | OK | 430 | – |
| EC2_hi | EC2=1.1 | NG | 401 | App.1 3.7-3.9 body in RV-BODY-FRONT/DRI-COOL/SIDEPOD/EC/TAIL/TAILPIPE/FLOOR-*: 281.3 cm3 out, max 9 mm at X 2546 (XR -854), Y 550, Z 181 |
| EC3_lo | EC3=-80 | OK | 356 | – |
| EC3_hi | EC3=20 | NG | 331 | App.1 3.7-3.9 body in RV-BODY-FRONT/DRI-COOL/SIDEPOD/EC/TAIL/TAILPIPE/FLOOR-*: 226.4 cm3 out, max 11 mm at X 1505 (XR -1895), Y 726, Z 368 |
| FB1_lo | FB1=16 | OK | 362 | – |
| FB1_hi | FB1=22 | NG | 337 | App.1 3.5 wake/floor boards in RV-FLOOR-*: 66.9 cm3 out, max 21 mm at X 1131 (XR -2269), Y 655, Z 146 |
| FB2_lo | FB2=700 | OK | 342 | – |
| FB2_hi | FB2=900 | NG | 341 | 3.8.1b sidepod to floor board [mm]: 48.1<br>App.1 3.5 wake/floor boards in RV-FLOOR-*: 0.1 cm3 out, max 2 mm at X 942 (XR -2458), Y 766, Z 342 |
| FB3_lo | FB3=300 | OK | 327 | – |
| FB3_hi | FB3=500 | OK | 333 | – |
| FB4_lo | FB4=0 | OK | 342 | – |
| FB4_hi | FB4=0.04 | OK | 380 | – |
| RH1_lo | RH1=20 | OK | 382 | – |
| RH1_hi | RH1=45 | OK | 370 | – |
| RH2_lo | RH2=60 | OK | 344 | – |
| RH2_hi | RH2=110 | OK | 336 | – |

24/34 통과, 7개 미검사.
