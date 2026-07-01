# gohome-auto — 텔레그램 출퇴근 자동화 봇

사내망 맥북에서 상시 실행되는 텔레그램 봇으로, 명령 한 번에 그룹웨어
(`gw.likelion.net`)에 자동 로그인 후 출근/퇴근을 처리한다.

- **트리거**: 텔레그램 명령 (`/checkout` 등)
- **자동화**: Playwright(Chromium) — 2단계 로그인 → 출퇴근 버튼 → 확인 모달
- **상시 실행**: macOS launchd (로그인 자동 시작 + 크래시 자동 재기동)

자세한 설계는 [`docs/PLAN.md`](docs/PLAN.md), 개발 단계는 [`TODO.md`](TODO.md) 참고.

---

## 텔레그램 명령어

| 명령어 | 동작 |
|--------|------|
| `/checkout` | **실제 퇴근** → "○월 ○일 ○시 ○분에 퇴근 처리되었습니다" + 스크린샷 |
| `/checkin` | **실제 출근** → 동일 형식 메시지 |
| `/checkout_test` | 퇴근 버튼→모달까지 확인 후 **취소** (실제 처리 X, 안전) |
| `/checkin_test` | 출근 버튼→모달까지 확인 후 **취소** (실제 처리 X, 안전) |
| `/status` | 봇 상태 (대기/처리 중) |
| `/start`, `/help` | 도움말 |

> 허용된 `TELEGRAM_CHAT_ID`(본인)의 명령만 처리한다.

---

## 프로젝트 구조

```
src/
  config.py      .env 로드 + 필수값 검증 + 비밀값 마스킹
  logger.py      파일/콘솔 로깅
  selectors.py   DOM 셀렉터 (사이트 변경 시 여기만 수정)
  automation.py  Playwright 2단계 로그인 + 출퇴근 처리
  bot.py         텔레그램 봇 (엔트리포인트)
scripts/
  com.gohome.bot.plist   launchd 등록 파일
docs/PLAN.md · TODO.md · logs/
```

---

## 최초 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env   # 값 채우기 (아래 참고)
```

### `.env` 설정
```dotenv
COMPANY_CODE=likelion        # 회사코드(로그인 화면에 고정 표시, 검증용)
USER_ID=...                  # 그룹웨어 아이디
USER_PW=...                  # 그룹웨어 비밀번호
GW_LOGIN_URL=https://gw.likelion.net/#/login?logout=Y&lang=kr
TELEGRAM_BOT_TOKEN=...       # BotFather 발급 토큰 (전용 봇!)
TELEGRAM_CHAT_ID=...         # 본인 chat_id
HEADLESS=true
DEFAULT_TIMEOUT_MS=30000     # SPA 렌더가 느려 30초 권장
MAX_RETRIES=3
```
> ⚠️ 텔레그램 봇은 **이 용도 전용으로 별도 생성**할 것. 다른 봇과 토큰을 공유하면
> 롱폴링이 충돌한다(토큰당 폴링 소비자는 1개만 가능).

---

## 수동 실행 / 테스트

```bash
# 로그인만 검증 (출퇴근 X)
.venv/bin/python -m src.automation login

# 퇴근 경로만 검증 (모달에서 취소, 실제 처리 X)
.venv/bin/python -m src.automation checkout-test

# 봇 직접 실행 (포그라운드)
.venv/bin/python -m src.bot
```

---

## 상시 실행 (launchd)

### 등록
```bash
cp scripts/com.gohome.bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.gohome.bot.plist
```

### 관리
```bash
launchctl list | grep gohome                 # 실행 상태 확인
launchctl unload ~/Library/LaunchAgents/com.gohome.bot.plist   # 중지
launchctl load   ~/Library/LaunchAgents/com.gohome.bot.plist   # 시작
```
코드/`.env` 수정 후에는 **unload → load**로 재기동한다.

- 실행 로그: `logs/automation.log`
- launchd stdout/stderr: `logs/launchd.out.log`, `logs/launchd.err.log`

> 전제: 맥북 상시 전원 + 클램쉘(덮개 닫아도 미절전). 잠자기 방어 로직은 없음.

---

## 트러블슈팅

| 증상 | 원인 / 조치 |
|------|-------------|
| 봇이 응답 없음 | `launchctl list \| grep gohome`로 실행 확인, `logs/launchd.err.log` 점검 |
| 로그인 타임아웃 | 사내망 연결 확인. SPA가 느리면 `DEFAULT_TIMEOUT_MS` 상향 |
| 요소 못 찾음 | 사이트 UI 변경 → `src/selectors.py` 갱신 |
| 다른 봇 메시지 가로챔 | 토큰 공유 금지 — 전용 봇 토큰 사용 |
| "권한 없음" 응답 | `TELEGRAM_CHAT_ID`가 본인 값인지 확인 |

---

## 보안

- 모든 비밀값은 `.env`에만 저장하고 git에서 제외한다(`.gitignore`).
- 로그에는 아이디/토큰이 마스킹되어 기록된다(비밀번호는 미기록).
- 봇은 허용된 `TELEGRAM_CHAT_ID`의 명령만 처리한다.
