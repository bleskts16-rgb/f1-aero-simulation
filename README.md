# F1 Aero Simulation

F1 셋업 파라미터(윙 각도, 라이드 하이트, 사이드포드 형상 등)를 바꿨을 때
**공력 성능이 어떻게 바뀌고, 그 결과 실제 서킷에서 랩타임이 얼마나 달라지는지**를
예측하는 프로젝트입니다.

```
셋업 파라미터 ─▶ 파라메트릭 CAD ─▶ OpenFOAM (대칭 반쪽 모델, RANS)
                                        │
                                        ▼
            랩타임 ◀─ QSS 랩 시뮬레이터 ◀─ 공력 서로게이트 (CL·A, CD·A)
                                        │
                                        ▼
                           웹 데모 (GitHub Pages, 브라우저 내 추론)
```

## 진행 상황

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | QSS 랩타임 시뮬레이터 + 실제 F1 텔레메트리 검증 | ✅ 1차 완료 |
| 2 | 파라메트릭 단순화 F1 형상 (OpenVSP / CadQuery) | ⏳ |
| 3 | OpenFOAM 자동 해석 파이프라인 (multi-fidelity) | ⏳ |
| 4 | 공력 서로게이트 학습 → 랩 시뮬 연결 | ⏳ |
| 5 | 웹 데모 + LLM 에이전트 | ⏳ |

## 1단계: 랩타임 시뮬레이터

**모델**: 질점(point-mass) 준정상(QSS) 모델
- 레이싱 라인: 트랙 중심선과 폭(TUMFTM racetrack-database)에서 최소 곡률 경로를 OSQP로 구합니다.
- 코너 한계 속도: 공력 다운포스와 타이어 하중 민감도를 반영한 횡방향 그립으로 계산합니다.
- 가속과 감속: 출력 한계, 구동축 트랙션, 마찰 타원, 공기저항, 구름저항을 고려합니다.
- 한 랩 계산 시간은 약 0.03초입니다.

**검증**: [FastF1](https://github.com/theOehrlein/Fast-F1)로 2024 예선 최고 랩의 속도 트레이스와 비교했습니다.

서킷마다 팀이 다른 공력 세팅을 쓰기 때문에, CL·A와 CD·A를 서킷별로 실제 속도 트레이스에 맞춰 역산했습니다.

| 서킷 | CL·A [m²] | CD·A [m²] | L/D | 실제 (예선 1위) | 시뮬 | 오차 |
|---|---|---|---|---|---|---|
| Monza | 6.14 | **1.36** (최저 드래그) | 4.52 | 1:19.327 (NOR) | 1:18.553 | −0.77 s |
| Budapest | **8.00** (최대 다운포스) | 1.89 | 4.24 | 1:15.227 (NOR) | 1:14.113 | −1.11 s |
| Suzuka | 6.50 | 1.84 | 3.53 | 1:28.197 (VER) | 1:27.803 | −0.39 s |
| Silverstone | 7.06 | 1.72 | 4.10 | 1:25.819 (RUS) | 1:25.754 | −0.06 s |

저드래그 서킷(Monza)과 최대 다운포스 서킷(Hungaroring)의 차이가 역산 결과에 그대로 나타납니다.
값은 질점 모델과 타이어 가정의 오차까지 흡수한 **유효값**입니다.

![validation](docs/figures/validation_speed_traces_calibrated.png)

**알려진 한계**
- ERS 에너지 한계(직선 끝 clipping), 기어 변속, DRS를 아직 반영하지 않았습니다.
- 질점 모델이라 공력 밸런스(앞뒤 다운포스 배분)의 영향은 보지 못합니다. 이후 2축(bicycle) 모델로 확장할 예정입니다.
- 트랙 데이터에 연석이 포함되지 않고 측량 노이즈가 있어, 곡률 평활화(σ = 8 m)를 적용했습니다.

## 사용법

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

python scripts/run_lap.py Monza --calibrated            # 한 랩 시뮬 + 그림
python scripts/run_lap.py Suzuka --cla 7.0 --cda 1.6    # 공력값 직접 지정
python scripts/validate.py Monza Suzuka --calibrated    # 실제 랩과 비교
python scripts/calibrate_aero.py Monza Budapest         # 서킷별 공력 역산
```

## 구조

```
lapsim/          랩타임 시뮬레이터 (track, vehicle, qss, reference)
scripts/         실행·검증·보정 스크립트
data/tracks/     서킷 중심선 데이터 (TUMFTM, LGPL-3.0)
cad/             파라메트릭 F1 형상 생성 (예정)
cfd/             OpenFOAM 케이스 템플릿 (예정, 결과 파일은 git 제외)
surrogate/       공력 서로게이트 모델 (예정)
web/             웹 데모 (예정)
docs/figures/    결과 그림
```

## 데이터 출처
- 서킷 형상: [TUMFTM/racetrack-database](https://github.com/TUMFTM/racetrack-database) (LGPL-3.0)
- 실제 랩 텔레메트리: [FastF1](https://github.com/theOehrlein/Fast-F1)
