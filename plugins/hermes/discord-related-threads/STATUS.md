# Current status

기준일: 2026-09-01

## 합의됨

- Hermes가 만들거나 참여한 쓰레드는 자동 인벤토리에 등록한다.
- 자동 인벤토리는 아직 발견하지 못한 쓰레드를 포착하고, 선택적 재알림은 이미
  본 쓰레드를 나중에 다시 보게 하는 2층 구조를 쓴다.
- 제어 명령은 `!s`/`!ㄴ` 확인, `!r Nd`/`!ㄱ Nㅇ` 재알림, `!r -`/`!ㄱ -`
  재알림 취소, `!c`/`!ㅊ` 종료로 정했다. N은 1~3650이다.
- 모든 인식된 명령 시도는 LLM 없이 결과 한 줄과 전체 명령 목록 한 줄을 보낸다.
- 첫 버전 명령은 `!s`, `!r`, `!c`와 한글 키 별칭으로 닫는다. 원본 명령은
  Discord에 남기되 원본·고정 확인 메시지 ID를 프로필 초기화까지 보존해 모든 향후
  Hermes 히스토리·LLM 문맥에서 제외한다. 메시지 본문은 별도 저장하지 않는다.
- 사용자 상호작용이 없는 쓰레드는 마지막 Hermes 활동의 현지 날짜에서 3일 뒤인
  정규 다이제스트 시각부터 후보가 된다. 실제 자동 보관 24시간 전이 더 빠르면 그
  시각부터 후보가 된다.
- 기존 `discord-related-threads` 플러그인의 `pre_gateway_dispatch` 훅에서 권한을
  확인한 뒤 제어 명령을 처리하고, 에이전트·LLM 경로는 건너뛴다.
- 원래 쓰레드에는 keepalive를 보내지 않고, 두 후보군을 지정 채널의 일일
  다이제스트로 다시 보여 준다.
- 확인 기준점 뒤의 새 Hermes 활동은 같은 3일/자동 보관 24시간 전 규칙으로 다시
  자동 발견 후보가 된다. `!c` 종료는 수동적 Hermes 활동만으로 풀리지 않으며,
  일반 사용자 메시지·유효한 확인·재알림 설정으로 다시 연다.
- 같은 쓰레드의 자동 발견과 재알림은 한 항목으로 합쳐 두 이유를 표시하고, 더 빠른
  기준 시각을 쓴다. 최대 10칸은 자동 5·재알림 5를 기본으로 하며 남는 칸은 다른
  후보군이 사용한다. 겹친 항목은 재알림 칸으로 센다.
- 조치 없는 항목은 성공한 노출 뒤 3일 후 다시 후보가 되며, 그보다 이르게 새로
  설정한 명시적 재알림이 있으면 예약 시각을 우선한다.
- 최초 활성화 때 영속 참여 기록의 기존 쓰레드를 기간 제한 없이 메타데이터만 모두
  가져온다. 자동 발견 기본 5칸은 신규 3·과거 가져오기 2를 기본으로 하며, 빈자리는
  상호 보충한다. 접근 불가 항목은 보존하되 일일 목록에서 제외하고 최초 결과를
  지정 채널에 한 번 요약한다.
- 제어 명령 확인·최초 가져오기 요약·다이제스트는 전송 전에 전달 장부에 기록한다.
  실패 시 1분, 5분, 30분, 이후 3시간 간격으로 재시도하며, 일일 다이제스트는 날짜가
  바뀌면 최신 목록으로 대체한다. 명령 상태 변경과 최초 가져오기는 재실행하지 않는다.
- 접근 불가 항목은 첫 7개 현지 날짜에는 매일, 이후에는 7일마다 다시 확인하고 자동
  삭제하지 않는다. 복구되면 과거 가져오기 후보로 되돌린다.
- 제어 명령 reaction은 `⏳` 처리 중, `✅` 장부 적용 성공, `❌` 미적용을 뜻한다.
  재시도된 명령 확인은 `↻ 지연 확인`, 다이제스트는 현지 날짜와 `재시도 N`으로
  표시한다. 원본 쓰레드 전달 중단은 지정 채널에 경고하고, 지정 채널 자체의 중단은
  로컬 로그와 복구 후 1회 경고로 남긴다.
- 다이제스트 항목은 쓰레드 링크와 `미확인`·`새 활동`·`과거`·`보관 임박`·`재알림`
  이유, 관련 시각만 한두 줄로 표시한다. 메시지 본문과 LLM 요약은 사용하지 않는다.
- 다이제스트는 최대 10개와 `외 N개`, 오전 9시 기본 일정, 최소 한 번 전달 정책을
  사용한다.
- 검토 전용 Discord 채널의 권장 이름은 `#hermes-review`로 정했다. 런타임은 이름을
  검색하거나 채널을 자동 생성하지 않고 설정된 `digest_channel_id`만 사용한다.
- 사람이 읽는 계약과 기능 구현은 `agent-extensions`의
  `plugins/hermes/discord-related-threads`가 단독 소유한다. 지원 릴리스는 수정하지
  않은 공식 Hermes의 호환 버전에 플러그인 하나만 설치하며, 개인 Hermes 포크나
  설치 시 코어 패치를 배포 의존성으로 두지 않는다. 필요한 새 호스트 기능은
  플러그인별 정책을 모르는 최소 범용 upstream 계약으로만 제안한다.
- 배포는 출처 커밋·파일 해시를 고정한 묶음만 사용하고, 게이트웨이를 멈춘 뒤 코드와
  SQLite를 백업한다. DB 마이그레이션은 추가 전용이며, 정상 코드 롤백 때 새 스키마는
  남기고 DB 무결성이 깨졌을 때만 백업 DB를 복원한다.
- 기존 `discord-related-threads` 플러그인은 계속 활성화하되 새 기능은
  `plugins.entries.discord-related-threads.thread_attention.enabled`가 없거나
  `false`면 시작하지 않는다. 실제 배포 때 `true`를 한 번 저장하면 재시작 뒤에도
  유지된다. 다이제스트 채널 ID는 필수이고, 기본 일정은 `09:00`과
  `Asia/Seoul`이다.
- `enabled: true`인데 다이제스트 채널 조회·전송 검증이 실패하면 새 기능만 설정 오류
  상태로 멈춘다. 기존 관계 기능과 일반 Hermes는 유지하고, 제어 명령은 LLM으로
  넘기지 않은 채 상태 변경 없이 `❌ 다이제스트 채널 설정 오류`와 전체 명령 목록으로
  끝낸다. source-thread reaction 권한만 없는 것은 활성화 차단 사유가 아니다.
- 정상 최초 활성화는 정적 설정, DB, Discord 채널을 차례로 검증하고 영속 활성화 ID와
  과거 가져오기 스냅샷을 고정한다. 실시간 수집을 먼저 연 뒤 과거분을 batch로
  처리하며, 완료 트랜잭션에서 최초 요약 의무를 한 번 만들고 다이제스트 스케줄을
  연다. 준비 완료일의 오전 9시가 지났으면 그날 보충 다이제스트를 한 번 실행하고
  과거 날짜별 다이제스트는 재생하지 않는다.

## 두 출처 개발 증명에서 구현·검증됨

- 플러그인 `1.1.0`은 기존 관계 도구·footer를 유지하면서 설정 parser, 추가 전용
  SQLite schema, 인벤토리·재알림·히스토리 제외·전달 장부 repository를 구현한다.
- 명령 parser와 고정 두 줄 응답, 권한 결과를 사용하는 선점 처리, reaction 전환,
  원본·확인 메시지 히스토리 격리와 LLM 우회가 연결되어 있다.
- 영속 참여 ID 스냅샷, 실시간 우선 수집, 재개 가능한 최초 가져오기, 1회 요약,
  접근 불가 재확인과 링크 가능한 항목의 일일 경량 메타데이터 갱신이 구현되어 있다.
- 후보 병합, 3일 재노출 제한, 5+5 가변 배분, 신규 3·과거 2 배분, 최대 10개와
  `외 N개`, 빈 다이제스트를 포함한 메타데이터 전용 렌더링이 구현되어 있다.
- 전달 장부는 최소 한 번 전송, 1분·5분·30분·3시간 재시도, 전날 다이제스트 대체,
  원본 전달 중단 경고와 다이제스트 채널 장애 1회 기록·복구 경고를 구현한다.
- 개발 증명용 Hermes 코어 기능 브랜치는 범용 `gateway_control_message`,
  `pre_gateway_dispatch`, `gateway_history_message`, `gateway_thread_participation`,
  `post_gateway_delivery`, `gateway_started`, `gateway_stopping` 경계와 Discord 공개
  메타데이터·전달 대상 검증 API를 제공한다.
- 플러그인 테스트 43개와 변경 경로를 묶은 Hermes 코어 회귀 테스트 399개가
  통과했다. 변경 Python 파일의 Ruff, bytecode compile과 두 작업 트리의
  `git diff --check`도 통과했다.
- 실제 Hermes `PluginContext`로 개발 플러그인을 교차 로드한 임시 프로필 스모크에서
  7개 게이트웨이 경계 등록, 명령 선점과 원본 히스토리 제외가 함께 통과했다.
- 검증한 플러그인 출처는 원격 main의 `0bd2f8d`, 대응 개발 증명용 Hermes 코어
  출처는 로컬 기능 브랜치의 `b20695a4cb`다. 이 코어 커밋은 원격 보존이나 배포
  대상이 아니라 stock-Hermes 플러그인 리팩터링의 비교 증거로 남긴다. 상세 결과는
  [개발 검증 기록](evidence/2026-08-30-thread-attention-development-verification.md)에
  남겼다.
- 기존 공개 `agent-skills` 저장소는 스킬과 플러그인을 함께 담는
  `agent-extensions`로 재구성되었고, `skills/`와 `plugins/hermes/`가 분리되어 있다.
- 이전 기준선의 임시 프로필 설치와 기존 관계 link/list/unlink 회귀 결과는
  `evidence/`에 보존되어 있다.

## 현재 호환성 차이

- 현재 작업 트리는 lifecycle, live participation과 bot delivery에 쓰던 증명용 훅
  4개를 등록 경계에서 제거했다. stock `register_platform_handler`, supervised task와
  unload cleanup으로 시작·관찰·정리를 소유하고, 공개 adapter 계약이 빠지면
  `compatibility_error`로 활성화를 거부한다.
- 플러그인 테스트는 46개가 통과했고, 수정하지 않은 공식 Hermes
  `e60983a697`의 실제 `PluginContext`에서 기존 도구, 남은 hook 4개, Discord handler
  factory 하나와 기본 비활성 상태를 확인했다. 현재 stock host에는
  `PluginContext.supports_hook`가 없으므로 probe는 strict 기능의 활성화를 명시적으로
  거부하며, 기존 관계 기능은 그대로 등록된다. 자세한 결과는
  [stock lifecycle 검증 기록](evidence/2026-09-01-stock-hermes-lifecycle-refactor.md)에
  남겼다.
- strict 요구사항 가운데 pre-coalescing 제어 분류, 일반 Hermes 인증 결과 재사용,
  모든 히스토리 재구성 경로의 메시지-ID 제외와 참여 ID·메타데이터·전달 대상용
  공개 Discord adapter 계약을 플러그인 정책 없는 최소 범용 변경으로 분리했다.
- 후보는 공식 `main` `21b2095d00` 기반 커밋 `bd853a945e`이며
  [NousResearch/hermes-agent#100004](https://github.com/NousResearch/hermes-agent/pull/100004)로
  제출했다. 이전 증명용 lifecycle·participation·delivery 훅은 포함하지 않고,
  `gateway_control_message`, `gateway_history_message`, 확장된 기존
  `pre_gateway_dispatch`, `PluginContext.supports_hook`와 세 Discord 공개 query만 둔다.
- 후보 host의 변경 경로 테스트는 155개가 모두 통과했다. 외부 플러그인을 임시
  `HERMES_HOME`에 로드한 스모크에서는 필수 hook과 Discord factory 등록이 통과했고,
  활성 설정 스모크에서는 `!ㅊ` 분류, agent dispatch 전 `skip`, 원본 ID의 history
  제외가 함께 통과했다. 자세한 결과는
  [upstream 후보 검증 기록](evidence/2026-09-01-upstream-host-contract-candidate.md)에
  둔다.
- PR이 아직 병합·릴리스되지 않았으므로 현재 공식 Hermes에는 여전히 strict 계약이
  없다. 개인 fork 브랜치는 기여 운반 수단이며 설치·배포 호환성 기준으로 사용하지
  않는다.
- 공개 모노레포 하위 디렉터리 설치는 임시 프로필에서 성공했다. Hermes 코어 업데이트는
  별도 `plugins/` 설치물을 보존하지만 플러그인 코드를 자동 갱신하지 않으며, 현재
  하위 디렉터리 설치본에는 `.git`이 없어 `hermes plugins update`도 사용할 수 없다.
  고정 커밋 재설치 절차는 [DEPLOYMENT.md](DEPLOYMENT.md)가 소유한다.
- 공개 저장소의 plugin 전용 CI는 Linux Python 3.11~3.13, macOS 3.11,
  Windows 3.11에서 단위 테스트·Ruff·bytecode compile을 모두 통과했다. 첫 검증 run은
  [33473106680](https://github.com/chriskimjj/agent-extensions/actions/runs/33473106680)이다.
- 공개 재사용 조건은 plugin manifest와 전용 `LICENSE`에 MIT로 명시했다.

## 라이브 상태

- 라이브 Hermes Agent와 `~/.hermes/plugins/discord-related-threads`에는 이번 개발본을
  설치하지 않았다.
- 라이브 설정, SQLite DB, 게이트웨이, Discord 채널과 예약 작업을 변경하지 않았다.
- 따라서 실제 Discord에서의 채널 권한 검증, 최초 가져오기, 명령·reaction,
  다이제스트 전송은 아직 실행하거나 관찰하지 않았다.

## 남은 개발 작업

- upstream PR의 CI·리뷰를 통과시키고, 계약 이름이나 payload가 바뀌면 플러그인의
  얇은 연결부와 compatibility probe를 함께 맞추기
- 병합 뒤 해당 계약이 포함된 첫 공식 Hermes 버전·커밋을 지원 기준으로 정하고,
  수정하지 않은 임시 Hermes 프로필에서 plugin-only install/activation 스모크와
  evidence를 남기기
- 공유 배포에서 플러그인 자체 업데이트를 자동화할 필요가 있으면 Hermes 하위 디렉터리
  updater 개선 또는 독립 root mirror 중 하나를 별도 결정하기. 그 전의 정식 절차는
  고정 커밋 `--force` 재설치다.
- 그 검증과 별도 라이브 배포 승인이 모두 끝난 뒤에만 `#hermes-review`의 실제 채널
  ID를 정하고 백업·설치·활성화·Discord 스모크·롤백을 수행하기

다음 실행 관문은 [NEXT.md](NEXT.md), 정확한 절차는
[DEPLOYMENT.md](DEPLOYMENT.md)가 소유한다.
