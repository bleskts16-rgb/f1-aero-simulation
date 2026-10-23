# CLAUDE.md

F1 셋업 → 파라메트릭 CAD → OpenFOAM → 공력 서로게이트 → QSS 랩타임으로 이어지는 개인 프로젝트.
진행 상황과 다음 할 일은 **[docs/worklog.md](docs/worklog.md)**에 날짜별로 적는다. 새 세션은 거기서 시작할 것.
서로게이트용 형상 계열(기준점 G1 v3, 설계 변수와 범위)은 **[docs/design_parameters.md](docs/design_parameters.md)**에 정리한다(2026-10-23 초안, 미확정).

## 작업 방식 (두 PC, 서로 다른 Claude 계정)
- 회사 PC와 집 PC에서 번갈아 작업한다. Claude 계정이 달라 대화·메모리는 공유되지 않는다.
  공유되는 것은 이 저장소(GitHub `main`)뿐이다.
- 세션 시작 때 `git pull`, 끝낼 때 커밋·push(사용자 확인 후). 작업 결과·결정은 `docs/worklog.md`에 남긴다.
- 커밋 작성자는 `bleskts16-rgb`로 맞춘다(저장소별 `git config user.name`).
- **저장소는 공개(PUBLIC)**다. 클러스터 주소·계정·회사 내부 정보는 코드·문서·커밋 어디에도 넣지 않는다.
  클러스터 접속은 환경변수 `F1CFD_HPC=user@host:port`로만 준다.

## 실행 환경
- 파이썬: 저장소의 `.venv` (`pip install -r requirements.txt`, CadQuery 포함).
- OpenFOAM v2512와 ParaView는 WSL Ubuntu에 있다. `scripts/run_cfd.py`가 케이스를 WSL 홈(`~/f1cfd/`)으로 복사해 돌리고, 로그와 힘만 되가져온다.
  `/mnt/c` 위에서 직접 돌리지 말 것(느림).
- Git Bash에서 WSL을 부를 때는 스크립트 파일을 만들어 `wsl.exe -e bash <file>`로 실행한다. 명령줄로 넘기면 `$변수`가 바깥에서 먼저 풀린다.
  경로 변환이 문제가 되면 `MSYS_NO_PATHCONV=1`을 쓴다.
- OpenFOAM에 들어가는 파일은 LF여야 한다(`.gitattributes`가 강제). 파이썬으로 쓸 때는 `write_bytes`나 `newline="\n"`을 쓴다.
- **무거운 해석(수백만 셀 이상)은 회사 클러스터(Slurm)에서, 가벼운 해석은 로컬에서** 한다. 집에서는 클러스터에 접근할 수 없다.
  클러스터에는 numpy가 없으므로 케이스는 로컬에서 만들어 `grid_study.py push`로 보낸다.
  공유 노드이므로 내 잡 전체 합을 동시 64코어 이하로 쓴다(노드별이 아님).

## 규칙
- 좌표는 FIA 규정과 같다: X 후방 +, Y 운전자 오른쪽 +, Z 위 +. CAD 원점은 앞차축, 노면은 Z = 0.
  CAD는 mm, CFD용 STL은 m.
- CFD는 Y ≥ 0 반쪽 모델이다. 힘은 ×2 해서 전체 차량 값으로 보고한다.
- **CL·A는 다운포스가 +** (`lapsim.Vehicle.cla`와 같음), CD·A는 항력 +. 기준 동압 q = ½·1.2·U², 기본 U = 50 m/s.
- CFD 정확도 목표(2026-10-19, `docs/results/aero_sensitivity_2026.md`): 코너 모드 CL·A ±2 %, CD·A ±2.5 %, 직선 모드 CD·A ±4 %.
  직선 모드 CL·A는 랩타임에 거의 영향이 없다. 격자 연구의 HF 판정은 이 기준으로 한다.
- CL·CD의 기준 면적은 baseline 전체 차량 정면 면적 1.474 m²(바퀴 포함, `cfd_report.py --aref`).
- 격자 단계 L1~L5는 배경 셀 0.40 m에서 1.33배씩 줄인 계열이다(`make_cfd_case.py`의 `LEVELS`). 단계마다 다른 설정은 바꾸지 않는다.
  격자 계열(scheme)은 `grid1`(층이 표면 셀에 비례)과 `grid2`(바닥·디퓨저 박스, 첫 층 0.8 mm 고정, 바퀴 레벨 5)가 있다. 서로 다른 scheme의 결과는 섞지 않는다.
- 클러스터 사용은 내 잡 전체 합이 동시 64코어 이하다(노드별이 아님). `grid_study.py`의 제출 웨이브가 이를 지킨다.
- 힘은 마지막 1000회 평균과 자기상관을 보정한 표준오차로 본다.
  Richardson 외삽·GCI는 단조 수렴이고 0.5 ≤ p ≤ 3이며 단계 간 변화가 통계 오차보다 클 때만 쓴다(`grid_study.py`가 판정).

## CAD 작업 규칙 (text-to-cad 참고, [docs/references/text-to-cad-f1.md](docs/references/text-to-cad-f1.md))
- 형상을 만들거나 고칠 때는 **`clean-cad` 스킬**([.claude/skills/clean-cad/SKILL.md](.claude/skills/clean-cad/SKILL.md))의 순서와 규칙을 따른다.
  순서: 브리프 → 스펙 → 2D 단면 확인 → 3D → QA → 렌더 체크리스트.
  프롬프트 틀은 [prompt-template.md](.claude/skills/clean-cad/references/prompt-template.md)에 있다.
- 형상을 바꾸면 `build_car.py`를 돌려 규정 점검과 `cad/qa.py` 검사(로프트 이탈, 양의 부피, 불리언 적합성, STL 닫힘)가 모두 OK인지 확인한다.
  NG가 있으면 exit 1이다. **계산 실패나 확인하지 않은 항목은 통과가 아니다.** 보고할 때 실제로 돌린 검사와 확인하지 않은 항목을 구분한다.
- **새 형상은 모두 2026 기준 볼륨을 만족해야 한다(2026-10-21 사용자 결정).** `cad/regvol.py`(App.1 본문 그대로)의 검사를 G0를 뺀 모든 형상에 강제하고, NG면 exit 1이다.
  설계 방식은 clean-cad 스킬 R1~R5(허용 공간을 먼저 그리고 그 안에 설계, 액티브 에어로 두 위치 확인, CAD 전용 볼륨에는 부품을 두지 않음)를 따른다.
  G0는 동결이라 같은 검사를 정보(`-- `)로만 출력한다. G0는 차체, 앞날개, 뒷날개, 바닥이 기준 볼륨을 벗어난 규정 미준수 형상이다.
  검사 범위는 차체(§8, §11~13, §15~16), 바닥(§4~7), 미러(§10), 앞날개(§17~22), 뒷날개(§25~27), 지지대(§31)다.
  형상 규칙(`shape_rule_checks`)도 같은 방식으로 강제한다: 앞날개 뒷전 아랫면 상승(3.10.1h), 뒷날개 뒷전 아랫면 각도 10/40/65°(3.11.1e),
  Floor Board 바깥 면 각도(3.5.4c, d), 사이드포드와 Floor Board 간격 50 mm(3.8.1b). 곡률과 단면 개수 규칙은 아직 없다.
- 형상을 바꾼 뒤에는 렌더를 직접 열어 확인한다. `render_car.py`(pyvista)는 깊이 정렬이 정확하고, `build_car.py`의 matplotlib 6면 그림은 빠른 확인용이다.
- 형상 수준: **G0**는 grid 연구의 기준이라 바꾸지 않는다(규정 기준 볼륨은 만족하지 않음). **G1**은 FIA 2026 공식 컨셉카 렌더를 닮게 하고, 2026-10-21부터 기준 볼륨을 모두 만족하도록 고친 형상이다(`--g1`, `--fia`).
- 형상을 바꾸지 않는 수정(검사, 리팩터)은 baseline STL 해시가 그대로인지 확인한다.
- 지정한 치수와 특징(필렛 반경, 슬롯 간격 등)을 조용히 줄이거나 빼지 않는다. 안 되면 보고한다.
- `third_party/text-to-cad/`는 읽기 전용 참고 자료다. 수치를 가져올 때는 좌표를 변환하고(x_우리 = −x_그쪽), 출처 커밋을 남긴다.

## 사용자 선호
- 답변은 한국어로 한다. 사용자는 코드를 읽을 수는 있지만 직접 작성하지는 않는다. 코드는 Claude가 쓰고, 설명은 목적 위주로 한다.
- 그래프는 학술 스타일(matplotlib, serif, 안쪽 눈금, 박스 축, 차분한 남색/적색). 표는 논문 부록 형식.
- 결과가 이상해 보이면 물리로 해석하기 전에 수치 설정(격자, 수렴, 경계조건)부터 의심하고 확인한다.
- 요청하지 않은 분석은 제안만 하고 임의로 돌리지 않는다.
- 커밋·push·클러스터 제출처럼 밖으로 나가는 작업은 사용자 확인 후에 한다.

## 자주 쓰는 명령
```bash
python scripts/build_car.py --half                                   # 반쪽 형상 + 규정 점검 (G0 baseline)
python scripts/build_car.py --half --details                         # 헤일로·서스펜션·웨이크 보드·미러 포함 (G0)
python scripts/build_car.py --half --fia                             # G1(FIA 렌더 스타일) + 상세 부품 → cad/out/fia2026_half
python scripts/render_car.py baseline_half fia2026_half              # pyvista 3D 렌더·비교 → docs/figures/render_*.png
python scripts/plot_regvol.py [--g0]                                 # 부품과 기준 볼륨 단면 비교 → docs/figures/regvol_sections_*.png
$env:F1_CAR="fia2026_half"; paraview --script=scripts/pv_car.py      # ParaView로 형상 보기 (PowerShell, 저장소 루트에서)
python scripts/run_lap_2026.py Monza                                 # 2026 규정 랩 (lapsim/rules2026.py)
python scripts/aero_sensitivity_2026.py                              # 공력 민감도 → CFD 정확도 목표
python scripts/make_cfd_case.py --level L1 --np 4                    # 로컬 케이스
python scripts/run_cfd.py cfd/runs/baseline_half_L1                  # WSL에서 메싱 + 해석
python scripts/cfd_report.py cfd/runs/baseline_half_L1 --aref 1.474  # 시간·메모리·CL/CD
python scripts/grid_study.py prepare|push|status|fetch|run-local|analyze <study>   # --scheme grid2 = 바닥 박스 + 고정 첫 층
python scripts/extract_ttc_reference.py                              # 참고 모델 바닥 수치표 → docs/references/
```
