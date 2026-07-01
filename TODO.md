# 개발 TODO — 출퇴근 자동화 봇

> `docs/PLAN.md` 기획안 기반 순차 개발 체크리스트.
> 위에서 아래로 진행하면 하나의 동작하는 봇이 완성됩니다.

## 0단계. 프로젝트 초기 세팅
- [x] Python 가상환경 생성 (`.venv`, 시스템 3.9.6 사용)
- [x] `requirements.txt` 작성 (`playwright`, `python-telegram-bot`, `python-dotenv`, `tenacity`)
- [x] 의존성 설치 (`pip install -r requirements.txt`)
- [x] Playwright 브라우저 설치 (`playwright install chromium`)
- [x] `.gitignore` 작성 (`.env`, `.venv/`, `logs/`, `__pycache__/`, `*.png`)
- [x] 폴더 골격 생성 (`src/`, `logs/`)

## 1단계. 설정 & 환경변수
- [x] `.env.example` 작성 (PLAN 7절의 키 목록)
- [x] 실제 `.env` 작성 (COMPANY_CODE/USER_ID/USER_PW/텔레그램, 커밋 금지)
- [x] `src/config.py` — `.env` 로드 및 필수값 누락 검증 (없으면 명확한 에러)
- [x] `src/logger.py` — 파일 + 콘솔 로깅 설정, 비밀값 마스킹 헬퍼

## 2단계. 웹 자동화 (Playwright) — 단독 실행 검증
- [x] `src/selectors.py` — 로그인 폼 실제 DOM 셀렉터 확정 (#reqCompCd/#reqLoginId/#reqLoginPw, 버튼 visible+정확일치)
- [x] `src/automation.py` — 브라우저 실행 → 로그인 URL 접속 뼈대
- [x] **2단계 로그인** 함수 구현 (회사코드 검증 → 아이디 → 다음 → 비번창 대기 → 비번 → 로그인)
- [x] 로그인 성공 판별 로직 (URL이 /login 벗어남 + networkidle)
- [x] SPA 대기 처리 적용 (visible/editable 대기, 하드코딩 sleep 지양)
- [x] dry-run(`login`) 모드로 로그인만 안전하게 검증 — **실제 로그인 성공 확인 완료** ✅
- [x] 출근/퇴근 버튼 실제 셀렉터 확정 (.worktime ul.btns li) + 확인 모달(확인/취소)
- [x] 출근/퇴근 클릭 → 모달 '확인' 클릭 흐름 구현 (`_do_action`, confirm 플래그)
- [x] 안전 test 모드(`checkout-test`)로 버튼→모달→취소 경로 검증 완료 ✅
- [x] 실패 시 스크린샷 저장 로직
- [ ] 실제 `checkout`(모달 확인)까지 1회 실행 검증 — 진짜 퇴근 기록되므로 사용자 타이밍에 실행

## 3단계. 재시도 & 예외 처리
- [ ] 로그인/클릭 단계 재시도 래핑 (`tenacity`, 최대 `MAX_RETRIES`, 지수 백오프)
- [ ] 타임아웃/요소 미발견 예외를 사용자 친화 메시지로 변환
- [ ] `finally`에서 브라우저·컨텍스트 항상 정리 (리소스 누수 방지)

## 4단계. 텔레그램 봇 연동
- [x] 기존 봇 재사용 (@sean_coin_auto_trading_bot) → 토큰 `.env` 반영
- [x] 본인 `chat_id`(8751407498) → `.env`의 `TELEGRAM_CHAT_ID` 설정
- [x] `src/bot.py` — 롱폴링 봇 + 시작 로그 (연결 확인 완료)
- [x] 인가 미들웨어: 허용된 chat_id 외 명령 차단
- [x] `/checkin`, `/checkout` (+ `_test` 안전버전) 핸들러 → `automation.py` 연결
- [x] `/status` 헬스체크 핸들러
- [x] 실행 결과 + 스크린샷 텔레그램 회신 (퇴근 시 "○월 ○일 ○시 ○분에 퇴근 처리되었습니다")
- [x] 동시 실행 방지 Lock + 비동기 처리
- [ ] 텔레그램에서 실제 명령 테스트 (/status, /checkout_test 먼저)

## 5단계. 상시 실행
- [ ] 봇을 장시간 실행 프로세스로 기동 (터미널/`nohup` 등)
- [ ] 며칠간 상시 대기하며 명령 정상 수신·처리되는지 확인
- [ ] (선택) 재부팅 후 자동 시작이 필요하면 launchd 등록 검토

## 6단계. 마무리
- [ ] `README.md` — 설치·설정·실행·트러블슈팅 정리
- [ ] 로그가 비밀값을 남기지 않는지 최종 점검
- [ ] 실사용하며 셀렉터 변경/실패 케이스 모니터링
