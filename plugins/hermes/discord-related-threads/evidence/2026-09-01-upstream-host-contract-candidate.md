# Upstream host contract candidate verification

검증일: 2026-09-01

## 범위와 출처

- 외부 플러그인 코드 기준: `agent-extensions` `d6249efcdb6031e59c21ddad5ca0e3774afaa6c0`
- 공식 Hermes 기준선: `NousResearch/hermes-agent` `main`
  `21b2095d00a98b8ad7b5c60b10587619c852cdb8`
- 범용 host 계약 후보: `bd853a945e46cf0cdf24db9530b8a6aa4cc514d2`
- upstream 제안:
  [NousResearch/hermes-agent#100004](https://github.com/NousResearch/hermes-agent/pull/100004)
- 후보는 별도 worktree와 개인 fork의 PR 브랜치에서만 다뤘다. 라이브
  `~/.hermes`, 게이트웨이와 Discord는 변경하지 않았다.

## 후보 계약

후보는 플러그인의 명령 문자, 장부 schema, 다이제스트 정책을 Hermes 코어에 넣지
않는다. 공식 surface에는 다음 일반 능력만 제안한다.

- `PluginContext.supports_hook(name)` 호환성 probe
- batching·busy merge 전 동기 `gateway_control_message` 분류
- core가 한 번 계산한 `is_authorized`와 공개 adapter를 기존
  `pre_gateway_dispatch`에 전달
- Discord recovery·backfill·recent context·resolved reply에 적용되는 동기
  `gateway_history_message` 필터
- Discord의 전체 영속 참여 ID snapshot, 본문을 반환하지 않는 쓰레드 metadata 조회,
  전달 대상 검증
- 플러그인이 소유한 제어 메시지에 대한 core reaction 억제

과거 증명용 `gateway_started`, `gateway_stopping`,
`gateway_thread_participation`, `post_gateway_delivery` 훅은 포함하지 않았다. stock
`register_platform_handler`, supervised task, unload cleanup과 Discord native listener가
그 수명주기·관찰 책임을 대신한다.

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| 후보 변경 경로 8개 테스트 파일 | 155 passed, 0 failed |
| 변경 Python Ruff | passed |
| `git diff --check` | passed |
| 외부 플러그인 등록 스모크 | passed |
| 활성 설정 control/history 통합 스모크 | passed |
| 후보 host `hermes plugins doctor --ci` | passed |
| 공개 plugin CI 5개 OS/Python 조합 | passed |
| broader gateway + plugin-manager 영역 | 7,430 passed, 8 failed, 40 skipped |
| exact-base 실패 파일 대조 | 같은 8개 실패 재현 |

등록 스모크는 임시 `HERMES_HOME`에서 실제 후보 `PluginContext`로 플러그인을 로드해
필수 hook과 Discord handler factory가 등록되는지 확인했다. 활성 설정 스모크는
`!ㅊ`가 control 메시지로 분류되고 기존 `pre_gateway_dispatch`에서 agent dispatch 전
`skip`되며, 같은 원본 메시지 ID가 history filter에서 제외되는 흐름을 확인했다. 두
스모크 모두 LLM이나 라이브 Discord를 호출하지 않았다.

후보 host를 `PYTHONPATH`로 고정한 실제 `hermes plugins doctor --ci`는 manifest를
읽고 1개 tool과 4개 hook의 선언·등록이 일치한다고 판정했다. 같은 plugin을 현재
공식 host에서 검사하면 `gateway_control_message`와 `gateway_history_message`를
unknown으로 거부했다. 이는 compatibility probe가 병합 전 host에서 fail closed하는
의도한 결과다.

플러그인 저장소의 commit `cb4b57dcf32763b2b23a4593d0acd440eaa5dd05`에서
[GitHub Actions run 33473470921](https://github.com/chriskimjj/agent-extensions/actions/runs/33473470921)을
실행했다. Ubuntu의 Python 3.11·3.12·3.13, macOS의 Python 3.11, Windows의
Python 3.11에서 각각 47개 behavior test, Ruff와 bytecode compile이 모두 통과했다.

broader 검증은 다음 공식 wrapper로 실행했다.

```bash
HERMES_PYTHON=<official-hermes-venv>/bin/python \
  scripts/run_tests.sh -j 8 tests/gateway/ tests/hermes_cli/test_plugins.py -q
```

실패한 8개는 후보가 수정하지 않은 6개 파일에 있었다. 정확한 기준선 커밋을 detached
worktree로 만든 뒤 그 6개 파일만 공식 wrapper로 재실행해 동일한 8개 실패를 확인했다.
원인은 macOS의 긴 경로·Unix socket 제약, readiness fixture 상태, shutdown diagnostic
spawn, 현재 환경에 없는 WeCom XML 선택 의존성이다. 후보와 직접 연결된 155개 테스트는
별도 재실행에서도 모두 통과했다.

## 설치와 업데이트 관찰

공개 저장소 하위 디렉터리 설치를 라이브와 분리된 임시 프로필에서 실행했다.

```bash
hermes plugins install \
  chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

설치는 성공했고 기본 비활성 상태로 끝났다. 설치 대상은 Hermes 코어 checkout 밖의
`<HERMES_HOME>/plugins/discord-related-threads`였으므로 코어 업데이트와 설치 보존은
분리된다. 그러나 하위 디렉터리를 임시 clone에서 꺼내 설치하는 현재 동작은 대상의
`.git`을 보존하지 않았다. 이어서 실행한
`hermes plugins update discord-related-threads`는 다음 이유로 실패했다.

```text
Plugin 'discord-related-threads' was not installed from git (no .git directory).
Cannot update.
```

따라서 현재 사실은 “Hermes 코어 업데이트가 설치된 플러그인을 지우지 않는다”이지,
“Hermes 업데이트가 플러그인 코드도 자동 갱신한다”가 아니다. 지원 배포의 현재 갱신
절차는 [DEPLOYMENT.md](../DEPLOYMENT.md)의 고정 커밋 재설치이며, 자동 plugin update는
별도 installer 개선이나 root-repository 배포 결정을 요구한다.

## 아직 증명되지 않은 것

- PR의 upstream 병합과 공식 Hermes 릴리스
- 병합된 공식 host에서의 최종 plugin-only activation smoke
- 실제 Discord 채널 권한, 과거 가져오기, reaction, 전달 재시도와 다이제스트
- 라이브 설치·업데이트·롤백

그러므로 이 기록은 merge-ready 후보와 비라이브 통합 증거이지, 지원 릴리스나 라이브
활성화 완료 증거가 아니다.
