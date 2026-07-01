"""텔레그램 봇 — 출퇴근 자동화 트리거.

로컬에서 상시 실행하며, 허용된 chat_id의 명령만 처리한다.

명령어:
  /checkin        실제 출근 처리
  /checkout       실제 퇴근 처리
  /checkin_test   출근 버튼→모달까지 확인 후 '취소' (실제 처리 안 함, 안전)
  /checkout_test  퇴근 버튼→모달까지 확인 후 '취소' (실제 처리 안 함, 안전)
  /status         봇 생존 확인
  /start, /help   도움말
"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .automation import ActionResult, run_action
from .config import load_config
from .logger import get_logger

log = get_logger("bot")
cfg = load_config()

# 동시에 두 개의 브라우저 자동화가 겹치지 않도록 직렬화
_run_lock = asyncio.Lock()

_LABEL = {"checkin": "출근", "checkout": "퇴근"}

HELP_TEXT = (
    "🦁 출퇴근 자동화 봇\n\n"
    "/checkin - 출근 처리\n"
    "/checkout - 퇴근 처리\n"
    "/checkin_test - 출근 경로만 검증(실제 처리 X)\n"
    "/checkout_test - 퇴근 경로만 검증(실제 처리 X)\n"
    "/status - 봇 상태 확인"
)


# ─────────────────────────────────────────────────────────────
# 인가: 지정된 chat_id만 허용
# ─────────────────────────────────────────────────────────────
async def _authorized(update: Update) -> bool:
    chat = update.effective_chat
    if chat is not None and chat.id == cfg.telegram_chat_id:
        return True
    log.warning(
        "인가되지 않은 접근 차단: chat_id=%s",
        chat.id if chat else "unknown",
    )
    if update.effective_message:
        await update.effective_message.reply_text("⛔ 이 봇을 사용할 권한이 없습니다.")
    return False


# ─────────────────────────────────────────────────────────────
# 메시지 포맷
# ─────────────────────────────────────────────────────────────
def _format_success(res: ActionResult) -> str:
    t = res.completed_at
    label = _LABEL[res.action]
    if not res.confirmed:
        return f"🧪 [테스트] {label} 버튼→확인 모달까지 정상 (취소로 종료 — 실제 처리 안 됨)"
    return f"{t.month}월 {t.day}일 {t.hour}시 {t.minute:02d}분에 {label} 처리되었습니다. ✅"


# ─────────────────────────────────────────────────────────────
# 핸들러
# ─────────────────────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    await update.effective_message.reply_text(HELP_TEXT)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    busy = _run_lock.locked()
    state = "🟡 처리 중" if busy else "🟢 대기 중"
    await update.effective_message.reply_text(f"봇 상태: {state}")


async def _handle_action(
    update: Update, action: str, confirm: bool
) -> None:
    if not await _authorized(update):
        return
    msg = update.effective_message
    label = _LABEL[action]

    if _run_lock.locked():
        await msg.reply_text("⏳ 이미 다른 요청을 처리 중입니다. 잠시 후 다시 시도하세요.")
        return

    async with _run_lock:
        note = "" if confirm else "(테스트) "
        await msg.reply_text(f"⏳ {note}{label} 처리 중… 로그인에 30초 정도 걸립니다.")
        try:
            res = await run_action(action, cfg=cfg, confirm=confirm)
        except Exception as exc:  # noqa: BLE001 - 사용자에게 원인 전달 목적
            log.exception("%s 자동화 실패", label)
            await msg.reply_text(f"❌ {label} 처리 실패: {exc}")
            await _try_send_error_shot(update, action)
            return

        await msg.reply_text(_format_success(res))
        await _try_send_photo(update, res.screenshot)


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_action(update, "checkin", confirm=True)


async def cmd_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_action(update, "checkout", confirm=True)


async def cmd_checkin_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_action(update, "checkin", confirm=False)


async def cmd_checkout_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_action(update, "checkout", confirm=False)


# ─────────────────────────────────────────────────────────────
# 스크린샷 전송 헬퍼
# ─────────────────────────────────────────────────────────────
async def _try_send_photo(update: Update, path) -> None:
    try:
        with open(path, "rb") as f:
            await update.effective_message.reply_photo(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("스크린샷 전송 실패: %s", exc)


async def _try_send_error_shot(update: Update, action: str) -> None:
    from .automation import SCREENSHOT_DIR

    shot = SCREENSHOT_DIR / f"error_{action}.png"
    if shot.exists():
        await _try_send_photo(update, shot)


# ─────────────────────────────────────────────────────────────
# 엔트리포인트
# ─────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(cfg.telegram_bot_token).build()

    app.add_handler(CommandHandler(["start", "help"], cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("checkout", cmd_checkout))
    app.add_handler(CommandHandler("checkin_test", cmd_checkin_test))
    app.add_handler(CommandHandler("checkout_test", cmd_checkout_test))

    log.info("텔레그램 봇 시작 — 롱폴링 대기 (허용 chat_id=%s)", cfg.telegram_chat_id)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
