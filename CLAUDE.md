# CLAUDE.md

F1 셋업 → 파라메트릭 CAD → OpenFOAM → 공력 서로게이트 → QSS 랩타임으로 이어지는 개인 프로젝트.
진행 상황과 다음 할 일은 **[docs/worklog.md](docs/worklog.md)**에 날짜별로 적는다. 새 세션은 거기서 시작할 것.

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
  공유 노드이므로 노드당 동시 64코어 이하로 쓴다.

## 규칙
- 좌표는 FIA 규정과 같다: X 후방 +, Y 운전자 오른쪽 +, Z 위 +. CAD 원점은 앞차축, 노면은 Z = 0.
  CAD는 mm, CFD용 STL은 m.
- CFD는 Y ≥ 0 반쪽 모델이다. 힘은 ×2 해서 전체 차량 값으로 보고한다.
- **CL·A는 다운포스가 +** (`lapsim.Vehicle.cla`와 같음), CD·A는 항력 +. 기준 동압 q = ½·1.2·U², 기본 U = 50 m/s.
- CL·CD의 기준 면적은 baseline 전체 차량 정면 면적 1.474 m²(바퀴 포함, `cfd_report.py --aref`).
- 격자 단계 L1~L5는 배경 셀 0.40 m에서 1.33배씩 줄인 계열이다(`make_cfd_case.py`의 `LEVELS`). 단계마다 다른 설정은 바꾸지 않는다.
- 힘은 마지막 1000회 평균과 자기상관을 보정한 표준오차로 본다.
  Richardson 외삽·GCI는 단조 수렴이고 0.5 ≤ p ≤ 3이며 단계 간 변화가 통계 오차보다 클 때만 쓴다(`grid_study.py`가 판정).

## 사용자 선호
- 답변은 한국어로 한다. 사용자는 코드를 읽을 수는 있지만 직접 작성하지는 않는다. 코드는 Claude가 쓰고, 설명은 목적 위주로 한다.
- 그래프는 학술 스타일(matplotlib, serif, 안쪽 눈금, 박스 축, 차분한 남색/적색). 표는 논문 부록 형식.
- 결과가 이상해 보이면 물리로 해석하기 전에 수치 설정(격자, 수렴, 경계조건)부터 의심하고 확인한다.
- 요청하지 않은 분석은 제안만 하고 임의로 돌리지 않는다.
- 커밋·push·클러스터 제출처럼 밖으로 나가는 작업은 사용자 확인 후에 한다.

## 자주 쓰는 명령
```bash
python scripts/build_car.py --half                                   # 반쪽 형상 + 규정 점검
python scripts/make_cfd_case.py --level L1 --np 4                    # 로컬 케이스
python scripts/run_cfd.py cfd/runs/baseline_half_L1                  # WSL에서 메싱 + 해석
python scripts/cfd_report.py cfd/runs/baseline_half_L1 --aref 1.474  # 시간·메모리·CL/CD
python scripts/grid_study.py prepare|push|status|fetch|analyze <study>
```
