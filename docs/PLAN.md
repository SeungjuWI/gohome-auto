# 출퇴근 자동화 봇 — 기획안 (PLAN)

## 1. 개요

사내망에 연결된 맥북에서 **상시 실행**되는 텔레그램 봇을 트리거로,
그룹웨어(`https://gw.likelion.net/#/`)에 자동 로그인 후 **출근/퇴근 버튼을 클릭**하는 웹 자동화 프로젝트.

- **트리거**: 로컬에서 항상 켜져 대기하는 Telegram Bot이 지정 명령어 수신
- **실행 주체**: Playwright(Python) 기반 브라우저 자동화
- **인증 방식**: 2단계 인증(OTP/모바일) 없음 → **매 실행마다 `.env`의 ID/PW로 신규 로그인** (세션 유지·쿠키 저장 불필요)
- **실행 환경 전제**: 맥북 상시 전원 연결 + 클램쉘(덮개 닫아도 미절전) 세팅 → **잠자기 방어 로직 불필요**, 봇은 그냥 계속 떠 있으면 됨

---

## 2. 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | |
| 웹 자동화 | Playwright (`playwright` for Python) | Chromium 사용, SPA 대기 처리 용이 |
| 트리거 봇 | `python-telegram-bot` (v21+, async) | 롱폴링 방식, 별도 포트 개방 불필요 |
| 환경변수 | `python-dotenv` | `.env`에서 비밀정보 로드 |
| 로깅 | 표준 `logging` + 파일 핸들러 | 실행 이력/실패 원인 추적 |
| 재시도 | `tenacity` | 로그인/클릭 재시도 |

---

## 3. 폴더 구조

```
gohome-auto/
├── README.md
├── requirements.txt
├── .env                    # 실제 비밀값 (git 제외)
├── .env.example            # 키 목록 템플릿 (git 포함)
├── .gitignore
├── docs/
│   ├── PLAN.md             # 본 기획안
│   └── TODO.md             # 개발 단계별 체크리스트
├── logs/                   # 실행 로그 (git 제외)
│   └── automation.log
└── src/
    ├── __init__.py
    ├── config.py           # .env 로드 및 설정값 검증
    ├── logger.py           # 로깅 설정
    ├── selectors.py        # DOM 셀렉터 상수 모음 (유지보수 분리)
    ├── automation.py       # Playwright 로그인 + 출퇴근 클릭 로직
    └── bot.py              # 텔레그램 봇 엔트리포인트 (명령어 핸들러)
```

---

## 4. 핵심 로직

### 4.1 텔레그램 봇 (`src/bot.py`)
- 롱폴링으로 **상시 대기** (프로세스가 켜져 있는 한 계속 명령 수신).
- **인가 검증**: `TELEGRAM_CHAT_ID`와 발신자 chat_id 일치 여부 확인 (타인 명령 차단).
- 명령어:
  - `/checkin` — 출근 처리
  - `/checkout` — 퇴근 처리
  - `/status` — 봇 생존 여부 확인 (헬스체크)
- 명령 수신 → `automation.py` 호출 → 결과(성공/실패/스크린샷)를 텔레그램으로 회신.
- 자동화 실행이 봇 이벤트 루프를 막지 않도록 비동기로 처리.

### 4.2 웹 자동화 (`src/automation.py`)
매 실행마다 아래 순서로 동작한다. (세션 재사용 없음)

1. Chromium 실행 (headless 여부는 설정값으로 토글).
2. `https://gw.likelion.net/#/` 접속.
3. **로그인**: `.env`의 ID/PW 입력 후 로그인 버튼 클릭.
4. 로그인 성공 확인 (대시보드 특정 요소 노출 대기).
5. **출근/퇴근 버튼** 탐색 후 클릭.
6. 처리 결과 확인 (완료 토스트/상태 텍스트 변경 대기).
7. 필요 시 스크린샷 저장 → 텔레그램 회신.
8. 브라우저 종료 (finally에서 반드시 정리).

---

## 5. 예외 처리 전략

### 5.1 SPA 지연 로딩 대기
- `page.wait_for_selector(state="visible")` / `wait_for_load_state("networkidle")` 활용.
- 임의 `sleep` 대신 **명시적 조건 대기** 사용.
- 요소별 타임아웃을 설정값으로 관리(`DEFAULT_TIMEOUT_MS`).

### 5.2 로그인/클릭 실패 재시도
- 로그인·버튼 클릭 단계를 **최대 N회(예: 3회) 재시도** (지수 백오프, `tenacity`).
- 재시도 실패 시 실패 사유 + 스크린샷을 텔레그램으로 통보.
- 매번 신규 로그인이므로 쿠키·토큰 저장 없음.

### 5.3 리소스 정리
- 성공/실패와 무관하게 `finally`에서 브라우저·컨텍스트를 항상 종료해 리소스 누수 방지.

---

## 6. 보안 고려사항

- **비밀정보는 전부 `.env`로 관리**하고 `.gitignore`에 등록:
  - `GW_USERNAME`, `GW_PASSWORD` — 그룹웨어 계정
  - `TELEGRAM_BOT_TOKEN` — 봇 토큰
  - `TELEGRAM_CHAT_ID` — 명령 허용 chat_id
- `.env.example`에는 **키 이름만** 두고 값은 비워 커밋.
- 봇 명령은 **허용된 chat_id에서만** 처리 (무단 출퇴근 조작 방지).
- 로그에 **비밀번호·토큰 평문 출력 금지** (마스킹).
- 사내망 정책 준수: 자동화 사용에 대한 내부 규정/승인 여부 확인 권장.

---

## 7. 환경변수 (`.env.example`)

```dotenv
# 그룹웨어 로그인
GW_USERNAME=
GW_PASSWORD=
GW_URL=https://gw.likelion.net/#/

# 텔레그램
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# 동작 설정
HEADLESS=true
DEFAULT_TIMEOUT_MS=15000
MAX_RETRIES=3
```

---

## 8. 범위 밖 (Out of Scope)

- 2단계 인증(OTP/모바일) 처리 — 대상 시스템에 없음.
- 쿠키/세션 영속화 — 매 실행 신규 로그인으로 대체.
- 잠자기·절전 방어 로직 — 상시 전원 + 클램쉘 세팅으로 불필요.
- 다중 사용자 지원 — 단일 사용자(본인) 전용.
- 정해진 시간 자동 실행(스케줄러) — 초기엔 수동 트리거만.
