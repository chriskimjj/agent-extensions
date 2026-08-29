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
gateway_control_message classifier ── keep out of batching / busy-session merge   │
          │                                                                       │
          ▼                                                                       │
pre_gateway_dispatch hook + core authorization result                             │
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
| Discord 어댑터 | 이벤트 정규화, 전체 참여 ID 기록, 전달 대상 검증, 메타데이터 조회, reaction 수명주기, 모든 히스토리 문맥 경로에서 플러그인이 제공한 범용 제외 판정 적용 | 관심 필요 여부 추론, 제어 명령 문법·장부 소유 |
| 최초 가져오기 작업 | 영속 참여 기록 전체의 메타데이터 멱등 등록, 링크 가능 상태 확인, 1회 결과 요약 | 메시지 원문 복사, 과거 쓰레드 keepalive |
| 자동 인벤토리 수집기 | Hermes 참여 쓰레드의 멱등 등록, 작업 활동 신호·확인 기준점 갱신, 자동 발견 기준 계산 | 원문 요약, keepalive |
| 범용 게이트웨이 훅 | 제어 이벤트의 batch·busy-session 병합 방지, 코어 권한 결과 전달, 참여·전송·시작·종료 신호와 히스토리 제외 질의 | 플러그인별 명령 문법·장부 상태 |
| `pre_gateway_dispatch` 훅 | 한/영 키 정규화, 인식된 제어 명령에 코어 권한 결과 적용, 단락 처리, 처리 결과 reaction 전환 | 일반 대화 추론 |
| `discord-related-threads` 플러그인 | 기존 관계 저장, 인벤토리·재알림 상태, 히스토리 제외 ID·판정, 고정 확인 템플릿 호스팅 | Hermes 코어 라우팅, 어댑터 내부 monkeypatch, 확인 문장 생성용 LLM |
| 쓰레드 인벤토리 | 발견·활동·확인 기준점·종료 상태의 기계적 진실 | 실제 읽음 여부, 대화 전문 |
| 재알림 장부 | 사용자가 명시한 다시 볼 시점 | 자동 발견 상태, 전달 증명 |
| 검토 작업 | 두 후보군 중복 제거, 3일 재노출 제한, 5+5 가변 배분, 신규 3·과거 2 기본 배분, 메타데이터 기반 한 줄 항목과 초과 개수 생성 | keepalive, 메시지 본문·전수 내용 요약 |
| Hermes 세션 저장소 | 에이전트 대화 기록 | 명시적 관심 상태 |
| 전달 장부 | 안정적 논리 키별 Discord 전달 의무, 시도 횟수·다음 시각·전달 중단 결과의 내구성 있는 기록 | 재검토 시점, 명령 상태 재적용 |
| 히스토리 제외 장부 | 처리한 원본 명령과 플러그인 확인의 Discord 메시지 ID를 프로필 초기화까지 보존 | 원문 보관, Discord 메시지 삭제, 일반 Hermes 답변 필터링 |
| Hermes 운영 로그 | 다이제스트 채널 자체가 불가할 때 원인·중단·복구 시각 기록 | 비공개 메시지 원문 저장, 대체 Discord 채널 추측 |

## 보안 경계

코어는 일반 게이트웨이 인증 결정을 한 번 계산한 뒤, 실제 차단·pairing보다 앞서
`pre_gateway_dispatch`에 불변 `is_authorized` 결과를 전달한다. 플러그인은 이 값이
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

## 범용 코어 연결 계약

Hermes 코어와 플러그인 사이의 공개 경계는 다음과 같다. 동기 분류·제외 훅은
awaitable을 허용하지 않고, 생명주기 훅은 동기·비동기 callback을 모두 허용한다.

| 경계 | 방향 | 계약 |
| --- | --- | --- |
| `gateway_control_message` | 어댑터 → 플러그인 | `platform`, `event`를 읽기 전용으로 분류한다. 참이면 batch와 바쁜 세션의 일반 텍스트 병합을 피하고 Discord 기본 reaction 대신 플러그인 수명주기를 쓴다. 주장한 플러그인은 같은 이벤트를 pre-dispatch에서 소비해야 한다. |
| `pre_gateway_dispatch` | runner → 플러그인 | `event`, `gateway`, `session_store`, 공개 `adapter`, 계산된 `is_authorized`를 전달한다. 인식된 명령은 `skip`으로 일반 에이전트 경로를 끝낸다. |
| `gateway_history_message` | Discord 어댑터 → 플러그인 | 정규화한 메시지·작성자·쓰레드 메타데이터로 제외 여부를 묻는다. 등록 callback 오류는 해당 메시지만 fail-closed 제외한다. |
| `gateway_thread_participation` | tracker → 플러그인 | 영속 참여 ID가 관찰됐음을 알린다. tracker 저장은 callback 성공 여부에 의존하지 않는다. |
| `post_gateway_delivery` | 어댑터 → 플러그인 | 성공한 일반 Hermes 응답의 이벤트, 반환 메시지 ID와 UTC 전달 시각을 알린다. |
| `gateway_started` / `gateway_stopping` | runner → 플러그인 | 연결된 어댑터 map과 함께 worker를 시작하고, 어댑터 종료 전 제한 시간 안에 정리한다. |

Discord 어댑터는 `participating_thread_ids()`,
`validate_delivery_target(channel_id)`,
`resolve_thread_metadata(thread_id, include_activity_history=...)`를 공개한다. 플러그인은
이 API와 기존 `send()`만 사용하며 Discord 어댑터 내부 구현을 패치하지 않는다.

## 소스와 배포 경계

사람이 읽는 제품·사양·아키텍처 계약과 플러그인 구현 코드의 권위는
`agent-extensions` Git 저장소의 이 디렉토리에 함께 둔다. Hermes Agent 코어의 범용
연결부만 전용 기능 브랜치와 깨끗한 worktree에 두며, 현재 대상은
`feat/discord-predispatch-thread-routing` 브랜치의
`~/.hermes/worktrees/discord-predispatch-thread-routing`이다.

- 도메인 기능, 상태, 플러그인 단위·통합 테스트는
  `plugins/hermes/discord-related-threads/`가 소유한다.
- Hermes Agent 변경은 플러그인별 명령을 알지 못하는 범용 제어 분류,
  pre-dispatch 권한 결과, 히스토리 제외, 참여·성공 전달 신호, 비동기 시작·종료 훅과
  Discord 공개 메타데이터 API로 제한한다. 그 코어 테스트는 Hermes Agent worktree가
  소유하며, 플러그인은 어댑터의 비공개 필드나 메서드를 monkeypatch하지 않는다.
- 라이브 `~/.hermes/plugins/discord-related-threads`와
  `~/.hermes/hermes-agent`는 개발 권위가 아니라 검증된 산출물의 배포 대상이다.
  라이브 파일에서 먼저 수정한 뒤 개발본으로 역복사하지 않는다.
- 플러그인과 코어 변경은 각자 소유 저장소에서 테스트하고, 함께 필요한 변경은 두
  출처 커밋을 배포 manifest에 고정한다. 통과 전에는 라이브 파일·DB, 게이트웨이와
  Discord를 변경하지 않는다.
- Git 개발본에는 자동 인벤토리와 재알림이 구현되어 있지만 라이브 플러그인에는 아직
  설치하지 않았다. 정확한 코드·DB 백업, 설치와 롤백 순서는
  [DEPLOYMENT.md](DEPLOYMENT.md)를 따른다.

이 경계의 근거와 결과는
[ADR-0003](docs/adr/0003-standalone-plugin-source-in-extensions-monorepo.md)에 둔다.

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
- 범용 히스토리 제외 연결부가 없거나 오류를 반환하면 플러그인 제어 명령을 일반
  LLM 입력으로 허용하는 방향으로 조용히 실패해서는 안 된다. 원본 실시간 진입은
  기존 `pre_gateway_dispatch` 단락을 유지하고, 히스토리 수집은 해당 메시지를
  제외한 채 원인을 로컬 운영 로그에 남긴다.
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
