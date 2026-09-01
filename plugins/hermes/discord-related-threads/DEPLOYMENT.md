# Deployment and rollback runbook

이 문서는 Hermes Discord Thread Attention의 설치와 복구 절차의 권위다. 정식
Stock-Hermes 배포와 병합 전 비라이브 프리뷰를 명확히 분리하며, 프리뷰 절차는
라이브 `~/.hermes` 배포를 허가하지 않는다.

## 배포 경로 구분

| 경로 | 용도 | Hermes 코어 | 프로필 |
| --- | --- | --- | --- |
| Stock-Hermes 플러그인 릴리스 | 지원 배포 | 호환 계약이 포함된 수정하지 않은 공식 릴리스 | 백업·승인된 라이브 프로필 가능 |
| 병합 전 프리뷰 설치 | 현재 전체 기능의 재현·평가 | 검토된 PR 커밋을 별도 Git 브랜치에 고정 적용 | 기본값이 아닌 전용 `HERMES_HOME`만 가능 |

아래 `배포 단위`부터의 일반 규칙은 Stock-Hermes 플러그인 릴리스를 뜻한다. 병합 전
프리뷰의 유일한 예외와 안전 경계는 바로 다음 절이 소유한다.

## 배포 단위

- 플러그인 배포는 깨끗한 `agent-extensions` 작업 트리의 커밋된 리비전에서만 만든다.
  미커밋 파일이나 라이브 파일을 배포 원본으로 사용하지 않는다.
- 지원 대상은 필요한 공개 플러그인 계약을 제공하는 수정하지 않은 공식 Hermes
  버전이다. 개인 fork, 로컬 기능 브랜치 또는 install-time Hermes 패치는 배포 단위에
  포함하지 않는다.
- 배포 묶음에는 플러그인 Git 커밋 SHA, 지원 Hermes 계약·버전, 생성 UTC 시각, 설치
  대상 상대 경로, 각 플러그인 파일의 SHA-256과 파일 스냅샷을 담은 manifest를 둔다.
  관찰한 Hermes Git SHA는 호환성 증거일 뿐 설치할 소스가 아니다.
- 토큰, 사용자 ID, `config.yaml`, SQLite DB와 비공개 메시지는 배포 묶음에 넣지
  않는다.
- 설치 과정은 Hermes Agent 코어와 Discord 어댑터 소스 파일을 수정하거나
  덮어쓰지 않는다. 호환성 probe가 실패하면 배포를 중단하고 라이브 소스를 패치해
  우회하지 않는다.

## 병합 전 프리뷰 설치(비릴리스)

이 경로는 [upstream PR #100004](https://github.com/NousResearch/hermes-agent/pull/100004)가
병합되기 전에 플러그인과 범용 호스트 연결구를 함께 평가하기 위한 것이다. 정식
릴리스, 일반 `hermes plugins install`, 라이브 배포 또는 장기 지원 포크가 아니다.

### 전제조건

- `agent-extensions`를 Git으로 clone한 깨끗한 작업 트리에서 실행한다. 기본값으로
  그 작업 트리의 현재 40자 커밋을 플러그인 원격 설치 pin으로 사용한다.
- `--hermes-root`는 Git 설치된 Hermes checkout의 루트여야 하고, 그 checkout에
  속한 venv의 `hermes --version`이 같은 설치 루트를 보고해야 한다.
- 별도의 깨끗한 Hermes checkout을 권장한다. helper는 connector가 건드리는 파일의
  변경은 중단하고, 그 밖의 worktree 변경은 개수를 경고한 뒤 stage하지 않은 채
  그대로 둔다.
- Hermes `HEAD`는 검증한 연결구 base
  `21b2095d00a98b8ad7b5c60b10587619c852cdb8`의 후손이어야 한다.
- `--hermes-home`은 사용자가 명시한 별도 프리뷰 프로필이어야 한다. helper는 기본
  라이브 경로 `~/.hermes`와 Hermes 소스 트리 내부 경로를 거부한다.
- 실제 토큰, 채널 ID와 설정은 helper가 읽거나 복사하지 않는다. 프리뷰 프로필에
  별도로 설정하는 일은 이 설치와 다른 승인 단계다.

### 계획 확인과 실행

저장소 루트에서 먼저 `--apply` 없이 실행한다. 이 단계는 경로, Hermes 실행 파일,
플러그인 pin과 만들 브랜치를 출력할 뿐 Git fetch나 설치를 수행하지 않는다.

```bash
python plugins/hermes/discord-related-threads/scripts/install_preview.py \
  --hermes-root /absolute/path/to/hermes-agent \
  --hermes-home /absolute/path/to/hermes-preview
```

Hermes venv가 표준 `.venv`/`venv` 위치가 아니라면 그 checkout에 속한 실행 파일을
명시한다.

```bash
python plugins/hermes/discord-related-threads/scripts/install_preview.py \
  --hermes-root /absolute/path/to/hermes-agent \
  --hermes-home /absolute/path/to/hermes-preview \
  --hermes-command /absolute/path/to/hermes \
  --apply
```

공개된 특정 플러그인 커밋을 재현하려면 `--plugin-ref`에 전체 40자 SHA를 넣는다.
생략하면 현재 깨끗한 `agent-extensions` checkout의 `HEAD`를 사용한다.

### helper가 수행하는 일

1. upstream PR ref에서 정확한 연결구 커밋
   `bd853a945e46cf0cdf24db9530b8a6aa4cc514d2`를 fetch하고 pin이 여전히 그 ref에
   포함되는지 확인한다.
2. base ancestry, 진행 중인 Git 작업, 충돌과 연결구 대상 파일의 로컬 변경을
   fail-closed로 검사한다. 다른 파일의 변경을 커밋에 섞지 않는다.
3. 연결구가 없다면
   `preview/discord-related-threads-bd853a945e` 브랜치를 만들고 `cherry-pick -x`로
   정확한 커밋 하나를 적용한다. 충돌하면 cherry-pick을 abort하고 원래 ref로
   돌아간다.
4. 지정한 프리뷰 `HERMES_HOME`에 공개 플러그인 커밋을 `--no-enable --ref`로
   설치한다.
5. 설치된 `discord-related-threads`에 `hermes plugins doctor --ci`를 실행한다.

helper는 config를 수정하거나 플러그인을 활성화하지 않고, gateway를 시작·중지하거나
Discord에 쓰지 않는다. Hermes dependency 설치와 공식 업데이트도 수행하지 않는다.
Doctor 실패는 사용 가능한 프리뷰로 간주하지 않는다.

### 복구와 중단

- connector 적용 전 실패는 Hermes branch와 프리뷰 프로필을 바꾸지 않는다.
- cherry-pick 충돌은 자동 abort되고 원래 branch 또는 detached HEAD로 돌아간다.
- connector 성공 뒤 plugin install 또는 Doctor가 실패하면 helper가 출력한 원래
  Git ref로 `git switch`한다. 별도 프리뷰 프로필의 플러그인은 활성화되지 않았으므로
  그대로 두어도 실행되지 않으며, 제거는 원인을 보존·확인한 뒤 별도 수행한다.
- 성공한 프리뷰를 끝낼 때도 helper가 출력한 원래 Git ref로 돌아가고 해당 프리뷰
  `HERMES_HOME`으로 Hermes를 실행하지 않는다. 기본 라이브 프로필에는 복구할 변경이
  없어야 한다.
- upstream PR이 바뀌어 pin이나 base 검증이 실패하면 새 커밋을 임의로 따라가지 않고,
  문서·테스트·evidence를 다시 검토해 새 pin을 커밋한다.

이 경로를 제공하기로 한 이유와 정식 릴리스 경계를 유지하는 근거는
[ADR-0005](docs/adr/0005-pinned-pre-merge-preview.md)가 소유한다.

## Hermes와 플러그인 업데이트의 구분

- Hermes 코어와 사용자 플러그인은 서로 다른 설치물이다. `hermes update`가
  `~/.hermes/hermes-agent`의 공식 코어를 갱신해도
  `~/.hermes/plugins/discord-related-threads`와 플러그인 SQLite는 별도 경로에 남는다.
  이것은 **설치 보존**이지 플러그인 코드의 자동 업데이트가 아니다.
- 호환되는 공식 Hermes로 갱신한 뒤 재시작하면 이미 설치된 같은 플러그인이 새 공식
  host 계약을 사용할 수 있다. 다만 플러그인의 새 커밋, manifest 또는 DB migration
  코드는 Hermes 업데이트가 가져오지 않는다.
- 2026-09-01 임시 프로필 검증에서 저장소 하위 디렉터리 설치는 정상 동작했지만,
  설치 대상에 `.git`이 보존되지 않았다. 따라서 현재 Hermes의
  `hermes plugins update discord-related-threads`는
  `was not installed from git (no .git directory)`로 종료된다.
- 지원 절차처럼 `--ref`로 설치하면 Hermes는 출처와 revision을 별도 metadata에
  보존하고 설치본을 pinned 상태로 표시한다. 이 경우 `hermes plugins update`는
  자동 이동을 명시적으로 거부하고 새 40자 SHA를 넣은 `install --force --ref`를
  안내한다. 어느 설치 방식도 Hermes 코어 업데이트에 plugin code 자동 갱신을
  결합하지 않는다.
- 이 모노레포 배포를 갱신할 때는 이 문서의 백업·호환성 검증을 먼저 수행한 뒤 고정
  커밋으로 계획된 재설치를 한다.

  ```bash
  hermes plugins install --force \
    --ref <agent-extensions의-40자-커밋-SHA> \
    chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
  ```

  `--force`는 자동 업데이트 대용으로 무심코 실행하는 명령이 아니다. 게이트웨이를
  멈추고 기존 플러그인 코드·설정·DB 백업과 manifest 검증을 끝낸 배포 단계에서만
  사용한다. 장래에 Hermes 하위 디렉터리 updater가 Git 출처 메타데이터를 보존하거나
  독립 루트 저장소 mirror를 정식 배포 경로로 채택하면 이 제한을 다시 검증한다.

## 백업 단위

각 실행은 다음과 같은 고유 디렉토리를 사용한다.

```text
~/.hermes/backups/hermes-discord-thread-attention/YYYYMMDDTHHMMSSZ-<short-sha>/
```

백업에는 다음을 둔다.

- `~/.hermes/plugins/discord-related-threads`의 코드·manifest 원본
- SQLite backup API로 만든
  `~/.hermes/discord-related-threads/relations.sqlite3`의 일관된 백업본
- 변경할 사용자 설정 파일이 있다면 그 원본
- 출처 커밋, 배포 묶음 해시, 백업 파일 해시와 단계별 결과를 담은 manifest

`__pycache__`, 토큰과 비공개 메시지 원문은 백업 manifest나 프로젝트 evidence에
복사하지 않는다. 백업 디렉토리는 모든 필수 파일과 해시를 검증하기 전에는 설치
단계로 넘어가지 않는다.

## 마이그레이션 규칙

- 스키마 변경은 `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ... ADD COLUMN`처럼 기존
  코드가 무시할 수 있는 추가 전용 변경만 허용한다.
- `DROP`, 이름 변경, 기존 열 축소, 기존 행 삭제·재작성은 첫 버전 배포에서 금지한다.
- 스키마 버전 확인과 모든 변경은 하나의 명시적 SQLite 트랜잭션에서 실행한다. 실패하면
  트랜잭션을 롤백하고 새 코드를 시작하지 않는다.
- 마이그레이션 전후에 `PRAGMA quick_check`가 `ok`인지 확인한다.
- 새 코드의 스모크 테스트가 실패해도 DB가 정상이라면 코드만 되돌리고 새 테이블과
  열은 남긴다. 이전 코드는 이 추가 스키마를 무시해야 한다.
- `quick_check` 실패처럼 DB 무결성이 깨진 경우에만 게이트웨이를 멈춘 상태에서 백업
  DB를 복원한다. 정상 DB를 단순 코드 롤백 때문에 과거 시점으로 되돌리지 않는다.

## 활성화 설정

- 새 코드는 기능 설정이 없을 때 비활성으로 설치한다. 코드 설치 자체가 자동 수집,
  과거 가져오기나 Discord 전송을 시작해서는 안 된다.
- 운영자가 Discord의 Hermes 관련 채널 묶음에 전용 채널을 만들 때 권장 이름은
  `#hermes-review`다. 배포 전 읽기 전용 검사에서 정확한 채널 ID와 Hermes 봇의
  조회·전송 권한을 확인하고, 이름이 아니라 그 ID를 설정에 넣는다. 플러그인이
  채널을 자동 생성하거나 이름으로 대상을 추측하게 하지 않는다.
- 기능을 실제로 켜는 배포에서는 [SPEC.md](SPEC.md)의 `설정과 활성화` 절에 정의한
  `plugins.entries.discord-related-threads.thread_attention` 블록을 기존
  `config.yaml`에 병합한다. 다른 plugin entry와 사용자 설정을 덮어쓰지 않는다.
- 다이제스트 채널 ID는 배포 묶음이나 evidence에 넣지 않고 라이브 프로필 설정에만
  둔다. 설정을 바꾸기 전에 `config.yaml` 원본을 실행별 백업에 포함한다.
- `enabled: true`는 설정 검증과 스모크 테스트를 수행할 준비가 된 배포에서 한 번만
  저장한다. 저장된 값은 재시작 뒤에도 유지되며 매번 다시 활성화하지 않는다.
- 게이트웨이를 시작하기 전에 YAML을 다시 읽어 구조, 필수 채널 ID, 시각과 시간대를
  검증한다. 실패하면 게이트웨이를 새 코드로 시작하지 않고 설정과 코드를 백업본으로
  복구한다.
- 정적 검증을 통과했지만 Discord 로그인 뒤 채널 조회·전송 권한 검증이 실패한 것은
  코드 배포 실패와 구분한다. 새 기능을 설정 오류 상태에 두고 수집·과거 가져오기와
  스케줄을 시작하지 않으며, 기존 플러그인 관계 기능과 일반 Hermes가 정상인지
  확인한다. 구현 회귀가 없다면 코드·정상 DB를 되돌리지 않고 채널 설정 또는 권한을
  고친 뒤 게이트웨이를 재시작한다.

## 설치 순서

1. `agent-extensions` 작업 트리가 깨끗하고 플러그인 대상 커밋이 존재하는지 확인한다.
2. 플러그인 단위·통합 테스트와 비라이브 DB 마이그레이션 테스트를 통과시킨다.
3. 수정하지 않은 공식 Hermes가 manifest의 지원 계약·버전을 만족하는지 호환성
   probe와 비라이브 스모크 evidence로 확인한다.
4. 배포 묶음을 만들고 manifest의 플러그인 파일 해시를 다시 검증한다.
5. 라이브 대상, 디스크 여유와 게이트웨이 제어 방법을 읽기 전용으로 검사한다.
   하나라도 실패하면 아무것도 변경하지 않는다.
6. Hermes 게이트웨이를 정상 종료하고 Discord 쓰기와 SQLite writer가 멈췄는지
   확인한다.
7. SQLite WAL을 checkpoint하고 `quick_check`를 실행한 뒤 코드·설정·DB 백업과 백업
   manifest를 만들고 검증한다.
8. 플러그인 코드는 같은 파일시스템의 임시 sibling 디렉토리에 준비해 해시를 확인한
   뒤, 게이트웨이가 멈춘 상태에서 manifest에 적힌 플러그인 파일만 원자적 파일
   교체로 설치한다. Hermes Agent 파일은 변경하지 않는다.
9. 추가 전용 DB 마이그레이션을 한 트랜잭션으로 실행하고 `quick_check`를 다시
   확인한다.
10. 실제 활성화 배포라면 권장 `#hermes-review` 채널을 사용할지 확인하고 정확한 채널
   ID를 얻은 뒤, 다른 설정을 보존한 채 합의된 `thread_attention` 블록을 병합한다.
   저장한 YAML을 다시 읽어 정적 설정을 검증한다.
11. 게이트웨이를 시작하고 프로세스 상태, 플러그인 로드, 호스트 호환성 probe, DB
    schema version과 다이제스트 채널 조회·전송 권한 검증 결과를 확인한다.
12. 첫 활성화라면 활성화 ID와 과거 가져오기 스냅샷이 한 번만 만들어졌는지,
    실시간 수집이 먼저 열린 뒤 batch가 진행되는지 확인한다. 완료 후 최초 요약
    전달 의무와 다이제스트 scheduler가 각각 한 번만 열렸는지 확인한다.
13. 지정한 폐기 가능 Discord 테스트 쓰레드에서 제어 명령 단락, 고정 확인,
    reaction, 상태 기록·취소와 LLM 미호출을 확인한다. 다이제스트 전송은 설정된 테스트
    대상에서 별도로 확인한다.
14. 초기화 중단·재시작 시험에서 같은 활성화 ID로 미완료 batch만 이어지고 요약과
    같은 날짜 다이제스트가 중복 생성되지 않는지 확인한다.
15. 성공 결과는 실제 사용자 ID와 메시지 본문을 제거해 `evidence/`에 남긴다.

## 실패 지점별 복구

- 게이트웨이 중지 전 실패: 변경하지 않고 종료한다.
- 백업 검증 전 실패: 설치하지 않고, 불완전한 백업은 실패 상태로 표시한다.
- 코드 설치 또는 마이그레이션 트랜잭션 실패: 게이트웨이를 멈춘 채 백업 코드·설정을
  복원한다. 실패한 DB 트랜잭션은 롤백하고 원래 게이트웨이를 시작한다.
- 마이그레이션 성공 뒤 시작·스모크 테스트 실패: 백업 코드·설정을 복원하되 정상인
  추가 스키마는 남기고, 원래 게이트웨이를 시작해 기존 기능을 다시 확인한다.
- 새 코드와 기존 기능은 정상이나 라이브 다이제스트 채널 검증만 실패: 설정 오류
  상태와 원인을 기록하고 자동 수집·전송을 시작하지 않는다. 임의 채널로 우회하거나
  코드를 반복 설치하지 않고 설정·권한을 수정한 뒤 정상 재시작한다.
- DB 무결성 실패: 게이트웨이를 멈춘 채 백업 DB와 코드·설정을 복원한 후
  `quick_check`가 `ok`일 때만 원래 게이트웨이를 시작한다.
- 복구 뒤에도 기존 게이트웨이가 정상화되지 않으면 반복 덮어쓰기를 하지 않고,
  백업·배포 manifest와 로컬 오류 로그를 보존한 채 수동 조사 상태로 전환한다.

롤백은 `git reset --hard`, 광범위한 디렉토리 삭제나 라이브 DB 테이블 삭제로
수행하지 않는다. 정확히 manifest에 기록된 대상만 백업본으로 복구한다.
