# Stock-Hermes lifecycle refactor verification

검증일: 2026-09-01

## 범위와 출처

- 플러그인: 이 evidence를 포함하는 `agent-extensions` revision의
  `plugins/hermes/discord-related-threads`
- stock Hermes host: `NousResearch/hermes-agent`의 로컬 `origin/main`
  `e60983a69730c058ce772829df3273aee6de3889`
- stock host는 detached 임시 worktree로 열었고 소스 파일을 수정하지 않았다.
- 라이브 `~/.hermes`, 게이트웨이와 Discord는 사용하지 않았다.

## 관찰 결과

| 검증 | 결과 |
| --- | --- |
| 플러그인 `unittest` 전체 | 46 passed |
| 변경 Python Ruff | passed (`ruff 0.15.10`) |
| Python bytecode compile | passed |
| `git diff --check` | passed |
| stock Hermes 실제 `PluginContext` 등록 | passed |

등록 스모크에서 확인한 사실은 다음과 같다.

- 기존 `discord_thread_links` 도구와 `transform_llm_output`이 유지됐다.
- lifecycle, live participation과 bot delivery용 증명 훅 4개를 더는 등록하지 않았다.
- stock `register_platform_handler("discord", ...)` factory가 정확히 하나 등록됐다.
- 새 기능은 기본 비활성 상태였고 task나 Discord listener가 등록 시점에 시작되지
  않았다. 등록된 Discord factory를 실제 호출해도 비활성 상태에서는 listener나
  worker가 생기지 않았다.
- stock `PluginContext`에는 아직 `supports_hook`가 없어서 compatibility probe가
  strict 기능을 활성화 불가로 판정했다. 기존 관계 도구와 footer 등록은 유지됐다.
- 남은 `gateway_control_message`와 `gateway_history_message`는 stock host에서 unknown
  hook 경고를 냈다. 이는 호스트 변경 없이 로드된다는 증거이자, strict 활성화에
  필요한 upstream 계약이 아직 없다는 증거다.

단위 테스트는 native Discord self-message가 Hermes 활동으로 기록되고 플러그인의
고정 확인 메시지는 활동에서 제외되는지, 공개 adapter 계약이 빠진 호스트가
`compatibility_error`로 활성화를 거부하는지, hook probe가 없는 호스트에서 인식된
제어 명령을 에이전트 경로로 흘리지 않는지도 확인했다.

## 검증 범위 밖

- 지원 가능한 stock Hermes에서의 thread-attention 활성화
- pre-coalescing 명령 분류, core authorization 결과와 전체 history filter의 stock
  통합 검증
- 실제 Discord 과거 가져오기, 전송, reaction과 다이제스트
- 라이브 설치와 롤백

따라서 이 기록은 plugin-only lifecycle 전환과 남은 호스트 계약 축소의 증거이지,
릴리스 또는 라이브 배포 완료 증거가 아니다.
