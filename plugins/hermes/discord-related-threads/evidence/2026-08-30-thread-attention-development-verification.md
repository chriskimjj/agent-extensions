# Thread Attention development verification

검증일: 2026-08-30

## 출처

- 플러그인: `chriskimjj/agent-extensions`의
  `0bd2f8db4e33ce0cb55af3f39c7a85381db0b3d5`
- Hermes 범용 코어 경계: 로컬
  `feat/discord-predispatch-thread-routing`의
  `b20695a4cb2699c74332faea80dce0302148a72e`
- Hermes upstream에 대한 현재 계정 권한은 read-only이고 사용자 fork는 아직 없어서,
  코어 커밋은 이 검증 시점에 원격으로 푸시하지 않았다.

## 통과 결과

| 검증 | 결과 |
| --- | --- |
| 플러그인 `unittest` 전체 | 43 passed |
| 변경 경로 Hermes 회귀 12개 파일 | 399 passed |
| 플러그인·코어 변경 Python Ruff | passed |
| Python bytecode compile | passed |
| 두 작업 트리 `git diff --check` | passed |
| 상대 Markdown 링크 검사 | passed |
| 실제 Hermes `PluginContext` 교차 로드 | passed |

교차 로드는 임시 `HERMES_HOME`과 가짜 Discord 식별자만 사용했다. 실제
`PluginContext`에 플러그인을 등록한 뒤 다음을 확인했다.

- 기존 `discord_thread_links` 도구와 7개 범용 게이트웨이 경계가 함께 등록됨
- 활성 설정에서 `!c`가 text batch 전에 제어 이벤트로 분류됨
- 같은 이벤트가 `pre_gateway_dispatch`에서 `skip`으로 단락됨
- 원본 명령 ID가 이후 `gateway_history_message` 판정에서 제외됨

## 실행 범위 밖

- 라이브 `~/.hermes` 설치·설정·DB 마이그레이션과 게이트웨이 재시작
- 실제 Discord 채널 생성, 채널 권한 검증, 메시지·reaction·다이제스트 전송
- 배포 manifest·백업 묶음과 라이브 롤백 연습

따라서 이 기록은 개발본의 코드·교차 경계 검증 증거이며 라이브 배포 증거가 아니다.
