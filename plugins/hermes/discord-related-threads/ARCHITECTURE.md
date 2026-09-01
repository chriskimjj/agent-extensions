# Architecture

## 런타임 흐름

```text
persisted participation records
              │
              ▼
initial historical backfill ──────────────────┐
                                              │
thread create / Hermes participation / recovery enumeration
              │                               │
              ▼                               │
automatic inventory collector ────────────────┤
                                              ▼
                                 profile-local thread inventory
                                              │
                                              └── automatic candidate ─────────────┐
                                                                                  │
exact one-letter control command                                                  │
          │                                                                       │
          ▼                                                                       │
official pre-coalescing classifier ── keep out of batching / busy-session merge   │
          │                                                                       │
          ▼                                                                       │
authorized pre-agent plugin boundary                                              │
          │                                                                       │
          ├── update seen/closed state in inventory                               │
          ├── update optional reminder ledger ────────────────────────────────────┤
          ├── enqueue deterministic result ──────────────┐                        │
          └── skip agent / LLM                             │                        │
                                                          │                        ▼
                                                          │            bounded daily digest
                                                          │                        │
                                                          └────────────────────────┤
                                                                                   ▼
                                                                        delivery outbox
                                                                           ├── source thread
                                                                           └── configured channel

ordinary user prompt ─────────────────────────▶ existing agent path
                         └─────────────────────▶ observed interaction signal
```

## 책임 경계

| 구성요소 | 책임 | 책임이 아닌 것 |
| --- | --- | --- |
| Discord | 메시지, 쓰레드 활동·보관 상태 | 사용자의 단순 열람 증명 |
| 공식 Hermes Discord 호스트 | 이벤트 정규화, 일반 권한 결정, 문서화된 plugin handler·action·task 연결, 제어 메시지의 병합 전 분리, 모든 히스토리 문맥 경로의 메시지-ID 포함 판정 | 관심 필요 여부 추론, 제어 명령 문법·장부 소유 |
| 최초 가져오기 작업 | 영속 참여 기록 전체의 메타데이터 멱등 등록, 링크 가능 상태 확인, 1회 결과 요약 | 메시지 원문 복사, 과거 쓰레드 keepalive |
| 자동 인벤토리 수집기 | Hermes 참여 쓰레드의 멱등 등록, 작업 활동 신호·확인 기준점 갱신, 자동 발견 기준 계산 | 원문 요약, keepalive |
| 공식 플러그인 API | native platform handler, supervised task, unload cleanup, normalized event와 capability-gated action을 안정된 계약으로 제공 | 플러그인별 명령 문법·장부 상태 |
| 최소 upstream 호스트 계약 | strict 요구사항에 필요한 병합 전 분류, 일반 인증 결과 재사용, 메시지-ID 히스토리 판정을 플러그인 불가지 범용 계약으로 제공 | thread-attention 정책·상태·Discord 문구 |
| `discord-related-threads` 플러그인 | 기존 관계 저장, Discord 관찰·메타데이터 조회, worker 수명주기, 인벤토리·재알림·전달·히스토리 제외 장부, 명령 처리와 고정 템플릿 | Hermes private adapter monkeypatch, 코어 소스 교체, 확인 문장 생성용 LLM |
| 쓰레드 인벤토리 | 발견·활동·확인 기준점·종료 상태의 기계적 진실 | 실제 읽음 여부, 대화 전문 |
| 재알림 장부 | 사용자가 명시한 다시 볼 시점 | 자동 발견 상태, 전달 증명 |
| 검토 작업 | 두 후보군 중복 제거, 3일 재노출 제한, 5+5 가변 배분, 신규 3·과거 2 기본 배분, 메타데이터 기반 한 줄 항목과 초과 개수 생성 | keepalive, 메시지 본문·전수 내용 요약 |
| Hermes 세션 저장소 | 에이전트 대화 기록 | 명시적 관심 상태 |
| 전달 장부 | 안정적 논리 키별 Discord 전달 의무, 시도 횟수·다음 시각·전달 중단 결과의 내구성 있는 기록 | 재검토 시점, 명령 상태 재적용 |
| 히스토리 제외 장부 | 처리한 원본 명령과 플러그인 확인의 Discord 메시지 ID를 프로필 초기화까지 보존 | 원문 보관, Discord 메시지 삭제, 일반 Hermes 답변 필터링 |
| Hermes 운영 로그 | 다이제스트 채널 자체가 불가할 때 원인·중단·복구 시각 기록 | 비공개 메시지 원문 저장, 대체 Discord 채널 추측 |

## 보안 경계

공식 Hermes 호스트는 일반 게이트웨이 인증 결정을 한 번 계산한 뒤, 에이전트 진입
전의 플러그인 경계에 불변 권한 결과를 전달한다. 플러그인은 이 값이
명시적으로 참인 Discord 쓰레드 명령만 장부에 적용하고, 권한 정책을 복제하거나
어댑터의 비공개 인증 메서드를 호출하지 않는다. 장부에는 토큰, 메시지 본문, 대화
내용이 아닌 최소 식별자와 상태만 둔다.

Discord의 앱 이벤트에는 Chris가 쓰레드를 단순히 열어 읽었다는 신호가 없다.
따라서 시스템은 사용자 메시지나 명시적 확인만 관찰 사실로 저장하고, 미열람을
확정적으로 주장하지 않는다.

자동 Discord 쓰기는 봇 계정만 사용한다. 일반 사용자 토큰으로 메시지를 보내는
self-bot은 설계 밖이다.

## 활성화 경계

`discord-related-threads` 플러그인의 기존 관계 기능과 새 쓰레드 관심 기능은 같은
프로세스에 있지만 별도 기능 스위치를 가진다. 새 기능의 설정 권위는 프로필 로컬
`config.yaml`의 `plugins.entries.discord-related-threads.thread_attention`이며,
정확한 키와 기본값은 [SPEC.md](SPEC.md)의 `설정과 활성화` 절이 소유한다.

코드 설치만으로 자동 수집이나 Discord 전송을 시작하지 않는다. 게이트웨이 시작 때
기능 스위치가 명시적으로 켜져 있고 설정 검증을 통과한 경우에만 최초 활성화 흐름에
진입한다. 이 분리는 미완성 설정이 기존 관계 기능이나 일반 Hermes 메시지를 중단하지
않게 하고, 배포 시점과 실제 데이터 수집·전송 시작 시점을 구분한다.

기능 스위치는 켜져 있으나 필수 다이제스트 채널 조회·전송 검증이 실패하면
쓰레드 관심 기능만 설정 오류 상태로 둔다. 이 상태에서는 수집·과거 가져오기·스케줄과
도메인 상태 변경을 멈추지만, 제어 명령 단락과 히스토리 제외라는 안전 통로는 유지해
인식된 명령이 LLM으로 새지 않게 한다. 기존 관계 기능과 일반 메시지 경로는 이
오류에 종속시키지 않는다. source-thread reaction은 최선 노력 UX이므로 그 권한만
없다는 이유로 전체 활성화를 막지 않는다.

정상 최초 활성화는 다음 영속 경계를 사용한다.

```text
static config → DB integrity/schema → Discord channel validation
                                           │
                                           ▼
                              durable activation + backfill snapshot
                                           │
                         ┌─────────────────┴─────────────────┐
                         ▼                                   ▼
                 live collector first              resumable backfill batches
                         │                                   │
                         └─────────────────┬─────────────────┘
                                           ▼
                                ready + one summary obligation
                                           │
                                           ▼
                              daily scheduler / same-day catch-up
```

활성화 ID와 과거 가져오기 스냅샷은 라이브 이벤트와 과거분의 분류 경계를 고정한다.
새 이벤트 수집을 먼저 열고 과거 batch를 뒤에서 처리하므로, 오래된 목록을 읽는 동안
생긴 새 쓰레드를 놓치지 않는다. `준비 완료` 전환과 최초 요약 전달 의무는 같은
트랜잭션에 두고, 재시작은 새 활성화를 만들지 않고 미완료 batch에서 이어 간다.
재활성화 때는 최초 스냅샷을 다시 열지 않되, 기능이 꺼져 있던 동안 tracker에 누적된
참여 ID를 현재 인벤토리와 한 번 대조해 누락분을 live 항목으로 등록한다.
접근 가능한 항목은 현지 날짜마다 한 번 링크·보관 메타데이터만 경량 재확인하며,
이 일일 갱신은 메시지 히스토리 스캔을 생략한다. 최초 가져오기 때만 제한된 최근
메시지의 작성자·시각을 확인하고 본문은 반환하거나 저장하지 않는다.

## 공식 호스트 호환 계약

지원 릴리스는 수정하지 않은 공식 Hermes가 제공하는 문서화된 plugin surface만
사용한다. 현재 stock surface에서 우선 재사용할 대상은 다음과 같다.

| 공식 surface | 플러그인 용도 |
| --- | --- |
| `pre_gateway_dispatch` 계열 정책 경계 | 인식된 제어 메시지를 에이전트·LLM 경로 전에 소비 |
| `register_platform_handler("discord", ...)` | 연결 시점에 Discord native event를 관찰하고 공개 SDK로 메타데이터를 조회 |
| `spawn_task(...)`와 unload cleanup | 전달 worker, 최초 가져오기와 일일 scheduler의 수명주기 관리 |
| `gateway_platform_event` | 정규화되어 제공되는 쓰레드 생성·이름 변경 등 관찰 |
| capability-gated platform actions | 지원되는 reaction 같은 Discord 동작 수행 |

strict 사양을 위 surface만으로 증명하지 못하는 경우에는 다음 **능력**만 Hermes
upstream에 일반 계약으로 제안한다.

- 정확한 제어 메시지를 Discord text batch와 busy-session 병합 전에 읽기 전용으로
  분류하는 능력
- 일반 Hermes와 같은 인증 결정을 복제 없이 인증 후 plugin consume 경계에서 쓰는 능력
- Discord 히스토리를 조립하는 모든 경로에서 메시지 ID별 포함 여부를 묻는 능력

현재 플러그인이 검증하는 최소 계약 초안은 아래와 같다. 이름이나 payload가 upstream
검토에서 달라질 수는 있지만, 그 경우 공식 릴리스 전에 플러그인의 얇은 연결부와
compatibility probe를 함께 바꾼다. 의미를 축소해 맞춘 척하지 않는다.

| 계약 초안 | 필요한 의미 |
| --- | --- |
| `PluginContext.supports_hook(name) -> bool` | 단순 등록 허용 여부가 아니라 해당 공식 Hermes가 그 hook의 fire-site와 공개 payload를 실제 제공하는지 판정한다. |
| 동기 `gateway_control_message` 분류 | `platform`과 원본 `MessageEvent`를 받고, Discord debounce·text batch·busy-session merge 전에 호출된다. `true`인 이벤트는 내용이 합쳐지지 않은 채 기존 `pre_gateway_dispatch`로 정확히 한 번 간다. |
| 확장된 `pre_gateway_dispatch` payload | 기존 skip/rewrite/allow 의미를 유지하면서, core가 한 번 계산한 불변 `is_authorized`와 해당 공개 adapter를 함께 준다. 플러그인은 인증 규칙을 다시 구현하지 않는다. |
| 동기 `gateway_history_message` 필터 | `platform`, `message_id`, 작성자 self/authorization 여부, chat 종류와 내용을 받고, Discord history/backfill/session 복원 등 에이전트 문맥을 만드는 모든 경로에서 호출된다. 제외 판정이나 필터 오류가 난 한 메시지는 문맥에 들어가지 않는다. |
| Discord `participating_thread_ids()` | Hermes의 영속 참여 tracker 전체를 안정된 ID snapshot으로 반환한다. 플러그인 설치 시점보다 오래된 항목도 포함하며 임의의 최근 N개 제한으로 잘리지 않는다. |
| Discord `resolve_thread_metadata(id, include_activity_history=...)` | 본문을 저장하지 않고 접근 가능 여부, guild/parent/thread 이름, 보관 상태·정책·시각과 필요한 경우 제한된 최근 활동 시각만 반환한다. |
| Discord `validate_delivery_target(id)` | 실제 전송 전에 채널 존재와 조회·전송 가능 여부를 구조화된 결과로 검증한다. 기존 공개 `send(...)`가 전송을 담당한다. |

플러그인은 지원하는 공식 계약을 시작 때 probe한다. 하나라도 없으면 기존 관계 기능은
유지하되 thread attention 활성화를 거부하고 필요한 호환 조건을 한 번 기록한다.
private adapter 접근, 메시지 삭제, 인증 규칙 복제 또는 기능 축소를 호환성 대체재로
사용하지 않는다.

## 소스와 배포 경계

사람이 읽는 제품·사양·아키텍처 계약과 전체 기능 구현 코드의 권위는
`agent-extensions` Git 저장소의 이 디렉토리에 함께 둔다. 릴리스는 공식 Hermes의
호환 버전과 이 플러그인 커밋 하나로 재현한다.

- 도메인 기능, 상태, 플러그인 단위·통합 테스트는
  `plugins/hermes/discord-related-threads/`가 소유한다.
- 부족한 호스트 계약은 플러그인별 명령과 정책을 모르는 최소 upstream Hermes 기여로
  분리한다. upstream에 합쳐진 공식 버전을 지원 기준으로 삼고, 그 변경의 Git SHA나
  patch를 플러그인 배포 묶음에 넣지 않는다.
- 라이브 `~/.hermes/plugins/discord-related-threads`는 검증된 플러그인 산출물의 배포
  대상이고, `~/.hermes/hermes-agent`는 수정하지 않는 공식 호스트 환경이다. 라이브
  파일에서 먼저 수정한 뒤 개발본으로 역복사하지 않는다.
- 플러그인 manifest는 플러그인 SHA와 지원 공식 Hermes 계약·버전을 기록한다. 설치는
  Hermes Agent 소스가 수정되지 않았음을 확인하며, 통과 전에는 라이브 파일·DB,
  게이트웨이와 Discord를 변경하지 않는다.
- 과거 로컬 `feat/discord-predispatch-thread-routing`의 `b20695a4cb`는 두 출처 개발
  증명의 재현과 upstream contract 축소에만 쓰는 evidence다. 축소된 현재 후보는 공식
  `main` 기반 `bd853a945e`이며
  [upstream PR #100004](https://github.com/NousResearch/hermes-agent/pull/100004)로
  제안했다. 개인 fork의 PR 브랜치는 기여 운반 수단일 뿐 지원 host나 live 배포물이
  아니다.
- Git 개발본에는 자동 인벤토리와 재알림이 구현되어 있지만 라이브 플러그인에는 아직
  설치하지 않았다. 정확한 코드·DB 백업, 설치와 롤백 순서는
  [DEPLOYMENT.md](DEPLOYMENT.md)를 따른다.

이 경계의 근거와 결과는
[ADR-0004](docs/adr/0004-stock-hermes-plugin-distribution.md)에 둔다.

## 실패와 동시성 원칙

- 자동 인벤토리 등록과 상태 갱신은 논리 키별로 멱등·원자적이어야 한다.
- 최초 가져오기가 중단되어도 재실행으로 이어갈 수 있어야 하며, 완료 요약을 여러
  번 성공 처리해서는 안 된다.
- 제어 명령 상태 변경과 확인 전달 의무, 최초 가져오기 완료와 요약 전달 의무는 각각
  같은 SQLite 트랜잭션에 기록한다.
- 제어 명령 상태 또는 문법 실패 결과와 원본 메시지의 히스토리 제외 ID도 같은
  트랜잭션에 기록해, 처리된 명령 시도가 나중의 문맥 수집으로 새지 않게 한다.
- 원본 Discord 메시지 ID를 멱등 키로 사용해 이벤트 재처리 시 명령 상태를 다시
  적용하지 않는다.
- 확인 기준점 전진, 종료·재개, 후보 병합과 마지막 노출 갱신은 같은 쓰레드의 동시
  이벤트에도 순서가 뒤집히지 않아야 한다.
- `⏳`는 처리 중에만 두고, DB 커밋 성공은 `✅`, 문법·DB 실패로 미적용된 결과는
  `❌`로 끝낸다. 확인 메시지 전송 실패는 이미 커밋한 `✅`를 바꾸지 않는다.
- 명령 결과와 전체 명령 목록은 한 곳의 고정 템플릿에서 만들어 서로 어긋나지 않게
  한다.
- 바쁜 쓰레드에서 큐에 들어간 제어 명령도 최종적으로 한 번 적용되어야 하며 LLM
  입력과 합쳐지면 안 된다.
- 게이트웨이 재시작은 커밋된 인벤토리와 재알림 상태를 잃게 해서는 안 된다.
- 최초 활성화 재시작은 같은 활성화 ID·과거 가져오기 스냅샷을 재사용해야 한다.
  완료된 batch, 최초 요약과 같은 현지 날짜의 성공한 다이제스트를 다시 만들지 않는다.
- Discord 권한 상실이나 삭제로 다시 열 수 없는 쓰레드는 정상 후보처럼 링크하지
  말고 별도 실패 상태로 관찰 가능해야 한다.
- 전달 장부는 실패 뒤 1분, 5분, 30분, 이후 3시간 간격을 내구성 있게 계산한다.
  일일 다이제스트는 현지 날짜가 바뀌면 전날 의무를 대체하고, 다른 전달 의무는
  성공할 때까지 이어 간다.
- 최소 한 번 전달에서 생길 수 있는 드문 중복을 견디되, 확인 메시지 재시도 때문에
  커밋된 상태 변경이나 최초 가져오기를 다시 실행하지 않는다.
- 확인 전송이 반환한 모든 Discord 메시지 ID는 전달 성공 기록과 함께 히스토리 제외
  장부에 남긴다. Discord 수신과 로컬 ID 기록 사이의 중단 창은 현재 봇이 작성한
  정확한 고정 확인 템플릿 보조 판별로 막는다.
- DB 실패나 원본 제외 ID 커밋 전 중단 창은 권한 있는 사용자의 메시지에 동일한
  결정적 제어 명령 시도 판별기를 읽기 전용으로 다시 적용해 막는다. 이 보조 판별은
  명령 상태를 실행하거나 전달 의무를 만들지 않는다.
- 필요한 공식 호스트 계약이 없으면 지원되는 척 조용히 실패해서는 안 된다. 호환성
  probe는 thread attention 활성화를 거부하고 원인을 로컬 운영 로그에 남기며,
  운영자는 지원 공식 Hermes 버전으로 올리기 전 기능을 사용하지 않는다.
- 설정 오류 상태에서도 같은 fail-closed 경계를 유지한다. 인식된 제어 명령은
  도메인 상태를 바꾸지 않고 고정 오류로 끝내며 일반 에이전트 경로로 되돌리지 않는다.
- 히스토리 제외 ID는 개수 기반 퇴거나 자동 TTL을 두지 않는다. 조회 시 DB 인덱스나
  제한된 메모리 캐시를 사용할 수 있지만, 프로필이 명시적으로 초기화되기 전까지
  내구성 있는 원본 판정은 유지한다.
- 접근 불가 항목은 첫 7개 현지 날짜에 매일, 이후 7일마다 다시 확인하고 자동
  삭제하지 않는다.
- 원본 쓰레드의 확정적 전달 불가는 지정 다이제스트 채널로 최소 경고를 라우팅한다.
  다이제스트 채널 자체가 불가하면 로컬 운영 로그에 남기고 복구 뒤 한 번 경고하며,
  임의의 대체 채널에는 쓰지 않는다.
