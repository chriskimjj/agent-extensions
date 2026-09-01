# Pre-merge preview installer verification

검증일: 2026-09-01

## 범위

upstream 계약이 병합되기 전에도 사용자가 실제 두 구성요소를 정직하게 재현할 수
있도록, 공개 플러그인 저장소에 비릴리스 preview helper를 추가했다. 이 검증은
라이브 설치나 공식 호환성 선언이 아니다.

고정 입력:

- upstream PR: `NousResearch/hermes-agent#100004`
- connector base: `21b2095d00a98b8ad7b5c60b10587619c852cdb8`
- connector commit: `bd853a945e46cf0cdf24db9530b8a6aa4cc514d2`
- 재적용 대상 공식 Hermes: `18a76be124d7c16ed98b629a358b23fef76a7f46`

## helper 계약

`scripts/install_preview.py`는 다음을 검증하거나 강제한다.

- `--apply`가 없으면 계획만 출력하고 Git fetch나 설치를 하지 않는다.
- 기본 라이브 `~/.hermes`와 Hermes checkout 내부의 `HERMES_HOME`을 거부한다.
- 실행한 Hermes command가 지정한 Git checkout의 설치물인지 `--version`으로 확인한다.
- plugin ref는 전체 40자 SHA만 허용하고, 생략 시 깨끗한 plugin checkout의 `HEAD`를
  사용한다.
- branch 이름은 `preview/` namespace에만 만들 수 있다.
- PR ref가 아직 고정 connector를 포함하고 Hermes HEAD가 검증 base의 후손인지
  확인한다.
- connector가 건드리는 host 파일에 로컬 변경이 있으면 중단한다.
- connector는 전용 branch에서 `cherry-pick -x`하며, 충돌 시 abort하고 원래 ref로
  돌아간다.
- plugin install은 지정한 profile에 `--no-enable --ref`로 실행하고 이어서 Plugin
  Doctor를 실행한다.
- config, gateway와 Discord를 변경하거나 실행하지 않는다.

## 자동 검증

플러그인 작업 트리에서 다음 결과를 확인했다.

- `python3 -m unittest discover -s tests -v`: 55 passed
- Ruff: passed
- `python3 -m compileall`: passed
- `git diff --check`: passed

추가된 Git integration test는 connector가 깨끗하게 적용되는 happy path, 같은 host
파일 충돌 시 원래 branch·HEAD 복구, live-profile 거부, branch namespace, full-SHA
pin, `--no-enable`와 profile-scoped install 환경을 실행해 검증한다.

## 최신 공식 Hermes 재적용

공식 `18a76be124`를 가리키는 폐기 가능한 격리 clone에서 helper의 실제
`prepare_connector` 경로를 실행했다.

- upstream PR ref fetch와 pin 확인: passed
- dedicated preview branch 생성: passed
- connector cherry-pick: passed
- resulting `git diff --check`: passed
- `scripts/run_tests.sh` 변경 경로 8개 파일: 155 passed, 0 failed

검증 대상은 base 후보 때와 같은 gateway/plugin-manager 회귀 파일이며, 실행은
Hermes가 요구하는 테스트 wrapper와 격리 환경을 사용했다. 임시 clone은 검증 뒤
폐기했다.

## 제외한 범위

- 라이브 `~/.hermes`와 현재 Hermes checkout 수정
- 실제 토큰·Discord ID·메시지·채널 사용
- gateway 시작·중지 또는 live plugin 활성화
- upstream merge 또는 공식 Hermes 호환성 floor 선언

## 공개 원격 확인

공개 commit `323e386f660b9c2bc3190d763e91d7eadf085df6`을 새 임시 clone으로 받은 뒤
helper를 `--apply` 없이 실행했다. helper는 plugin ref를 동일한 공개 40자 SHA로
해석하고 connector pin·전용 profile·branch 계획을 출력한 뒤 Git fetch나 설치 없이
종료했다.

[GitHub Actions run 33505771312](https://github.com/chriskimjj/agent-extensions/actions/runs/33505771312)는
다음 5개 작업에서 모두 통과했다.

- Ubuntu / Python 3.11, 3.12, 3.13
- macOS / Python 3.11
- Windows / Python 3.11
- 각 작업: 55 behavior tests, Ruff, compileall

helper의 `--apply` 전체 경로는 host Git 적용과 plugin install 두 단계로 분리해
검증했다. 실제 공개 plugin commit의 원격 하위 디렉터리 설치·후보-host Doctor는
기존 [upstream 후보 검증](2026-09-01-upstream-host-contract-candidate.md), 최신 공식
Hermes의 connector 적용·회귀는 이 문서의 앞 절이 증명한다. 라이브 profile에서 두
단계를 합쳐 실행하지 않았다.
