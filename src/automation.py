"""Playwright 웹 자동화 — 2단계 로그인 + 출퇴근 클릭.

로그인 흐름:
  1단계) 로그인 URL 접속 → 회사코드(읽기전용 'likelion', 검증만) + 아이디 입력 → '다음'
  2단계) 비밀번호 입력창이 DOM에 완전히 로딩·표시될 때까지 대기 → 비밀번호 입력 → '로그인'

핵심 원칙:
- 자격정보는 전부 config(.env)에서만 읽는다. 코드에 하드코딩 금지.
- SPA 지연 로딩 대비: 하드코딩 sleep 대신 요소의 visible/editable 상태를 명시적으로 대기.
- 성공/실패와 무관하게 브라우저 리소스를 finally에서 항상 정리.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.async_api import (
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from . import selectors
from .config import Config, load_config
from .logger import get_logger

log = get_logger("automation")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "logs"


class AutomationError(RuntimeError):
    """자동화 단계에서 복구 불가한 실패."""


@dataclass
class ActionResult:
    """자동화 실행 결과. 봇이 사용자에게 회신할 때 사용한다."""

    action: str  # "checkin" | "checkout"
    login_only: bool
    confirmed: bool  # 모달 '확인'까지 눌러 실제 처리했는지
    completed_at: datetime  # 처리 완료(로컬) 시각
    screenshot: Path


# ─────────────────────────────────────────────────────────────
# 로그인 (2단계)
# ─────────────────────────────────────────────────────────────
async def _login(page: Page, cfg: Config) -> None:
    timeout = cfg.default_timeout_ms

    log.info("로그인 페이지로 이동: %s", cfg.gw_login_url)
    await page.goto(cfg.gw_login_url, wait_until="domcontentloaded")

    # --- 1단계: 회사코드(검증) + 아이디 입력 → 다음 ---
    log.info("[1단계] 아이디 입력 화면 대기")
    id_input = page.locator(selectors.USER_ID_INPUT).first
    await id_input.wait_for(state="visible", timeout=timeout)

    # 회사코드는 'likelion'이 이미 채워진 읽기전용 박스 → 타이핑하지 않고 값만 검증.
    await _verify_company_code(page, cfg)

    log.info("[1단계] 아이디 입력")
    await id_input.fill(cfg.user_id)

    log.info("[1단계] '다음' 클릭")
    await _click_next(page, timeout)

    # --- 2단계: 비밀번호 입력창이 완전히 로딩/표시/편집가능해질 때까지 확실히 대기 ---
    log.info("[2단계] 비밀번호 입력창 로딩 대기")
    pw_input = page.locator(selectors.PASSWORD_INPUT).first
    # (1) DOM 부착 + 표시 대기
    await pw_input.wait_for(state="visible", timeout=timeout)
    # (2) 편집 가능(활성화)해질 때까지 대기 — 애니메이션/비활성 상태 방지
    await page.wait_for_function(
        """() => {
            const el = document.querySelector('input[type=password]');
            return el && !el.disabled && el.offsetParent !== null;
        }""",
        timeout=timeout,
    )

    log.info("[2단계] 비밀번호 입력")
    await pw_input.fill(cfg.user_pw)

    log.info("[2단계] '로그인' 클릭")
    await _click_login(page, timeout)

    # --- 로그인 성공 판정 ---
    await _verify_logged_in(page, cfg)
    log.info("로그인 성공")


async def _verify_company_code(page: Page, cfg: Config) -> None:
    """읽기전용 회사코드 박스가 기대값과 일치하는지 확인(있을 때만)."""
    try:
        box = page.locator(selectors.COMPANY_CODE_INPUT).first
        await box.wait_for(state="attached", timeout=3000)
        value = (await box.input_value()).strip()
        if value and value != cfg.company_code:
            log.warning(
                "회사코드 값이 기대와 다릅니다 (화면=%r, .env=%r)",
                value,
                cfg.company_code,
            )
        else:
            log.info("회사코드 확인: %s", value or "(빈 값)")
    except PlaywrightTimeoutError:
        # 읽기전용 박스를 못 찾아도 로그인 자체는 진행 (셀렉터 점검 필요할 수 있음)
        log.info("회사코드 박스를 찾지 못함 — 검증 건너뜀 (selectors 점검 권장)")


async def _click_next(page: Page, timeout: int) -> None:
    """'다음' 버튼 클릭 (보이는 정확 텍스트 버튼만)."""
    await page.locator(selectors.NEXT_BUTTON).first.click(timeout=timeout)


async def _click_login(page: Page, timeout: int) -> None:
    """'로그인' 버튼 클릭 (보이는 정확 텍스트 버튼만)."""
    await page.locator(selectors.LOGIN_BUTTON).first.click(timeout=timeout)


async def _verify_logged_in(page: Page, cfg: Config) -> None:
    """로그인 성공 여부 확인.

    성공 판정: URL이 '/login'을 벗어남 (SPA 라우팅이 메인으로 이동).
    """
    timeout = cfg.default_timeout_ms
    try:
        await page.wait_for_function(
            "() => !location.hash.includes('login')", timeout=timeout
        )
    except PlaywrightTimeoutError:
        raise AutomationError(
            "로그인 실패 추정 — 로그인 화면을 벗어나지 못했습니다 "
            "(아이디/비밀번호 오류 또는 추가 인증 단계 존재 가능)."
        )
    # 로그인 후 네트워크 안정화까지 잠시 대기 (SPA 데이터 로딩)
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        log.info("networkidle 대기 타임아웃 — 계속 진행")


# ─────────────────────────────────────────────────────────────
# 출근 / 퇴근 클릭
# ─────────────────────────────────────────────────────────────
async def _do_action(
    page: Page, action: str, cfg: Config, confirm: bool = True
) -> None:
    """출근/퇴근 버튼 클릭 → 확인 모달에서 '확인'(또는 test 모드는 '취소') 클릭.

    confirm=False 이면 모달에서 '취소'를 눌러 **실제 처리 없이** 경로만 검증한다.
    """
    timeout = cfg.default_timeout_ms
    if action == "checkin":
        sel, label = selectors.CHECKIN_BUTTON, "출근"
    elif action == "checkout":
        sel, label = selectors.CHECKOUT_BUTTON, "퇴근"
    else:
        raise AutomationError(f"알 수 없는 동작: {action!r} (checkin/checkout만 지원)")

    log.info("[%s] 버튼 대기 및 클릭", label)
    btn = page.locator(sel).first
    await btn.wait_for(state="visible", timeout=timeout)
    await btn.scroll_into_view_if_needed()
    await btn.click(timeout=timeout)

    # 확인 모달 등장 대기 ('~ 하시겠습니까?')
    log.info("[%s] 확인 모달 대기", label)
    try:
        await page.locator(selectors.MODAL_MARKER).first.wait_for(
            state="visible", timeout=timeout
        )
    except PlaywrightTimeoutError:
        raise AutomationError(
            f"[{label}] 확인 모달이 뜨지 않았습니다 (셀렉터 불일치 또는 상태 문제)."
        )

    if not confirm:
        log.info("[%s] test 모드 — 모달 '취소' 클릭 (실제 처리 안 함)", label)
        await page.locator(selectors.MODAL_CANCEL_BUTTON).first.click(timeout=timeout)
        return

    log.info("[%s] 모달 '확인' 클릭 (실제 처리)", label)
    await page.locator(selectors.MODAL_CONFIRM_BUTTON).first.click(timeout=timeout)

    # 모달이 닫히면 처리 완료로 간주
    try:
        await page.locator(selectors.MODAL_MARKER).first.wait_for(
            state="hidden", timeout=timeout
        )
        log.info("[%s] 처리 완료 (모달 닫힘)", label)
    except PlaywrightTimeoutError:
        log.warning("[%s] 모달이 닫히지 않음 — 결과 스크린샷으로 확인 필요", label)


# ─────────────────────────────────────────────────────────────
# 진입점: 브라우저 수명주기 관리
# ─────────────────────────────────────────────────────────────
async def run_action(
    action: str,
    cfg: Config | None = None,
    login_only: bool = False,
    confirm: bool = True,
) -> ActionResult:
    """로그인 후 지정 동작(checkin/checkout)을 수행하고 결과 스크린샷 경로를 반환.

    login_only=True 이면 **로그인까지만** 수행하고 출퇴근 클릭은 하지 않는다(dry-run).
    confirm=False 이면 출퇴근 버튼→모달까지 가되 '취소'를 눌러 실제 처리는 하지 않는다.
    로그인/셀렉터/모달 경로를 실제 출퇴근 없이 안전하게 검증할 때 사용한다.

    실패 시 실패 시점 스크린샷을 남기고 예외를 올린다.
    """
    cfg = cfg or load_config()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "login" if login_only else action
    shot_path = SCREENSHOT_DIR / f"result_{tag}.png"

    playwright: Playwright | None = None
    browser: Browser | None = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=cfg.headless)
        context = await browser.new_context()
        context.set_default_timeout(cfg.default_timeout_ms)
        page = await context.new_page()

        await _login(page, cfg)
        if login_only:
            log.info("dry-run: 로그인만 수행하고 출퇴근 클릭은 건너뜁니다")
        else:
            await _do_action(page, action, cfg, confirm=confirm)

        completed_at = datetime.now()
        await page.screenshot(path=str(shot_path))
        log.info("결과 스크린샷 저장: %s", shot_path)
        return ActionResult(
            action=action,
            login_only=login_only,
            confirmed=(not login_only and confirm),
            completed_at=completed_at,
            screenshot=shot_path,
        )

    except Exception as exc:
        # 실패 스크린샷 확보 (가능한 경우)
        try:
            if "page" in locals():
                fail_path = SCREENSHOT_DIR / f"error_{tag}.png"
                await page.screenshot(path=str(fail_path))  # type: ignore[name-defined]
                log.error("실패 스크린샷 저장: %s", fail_path)
        except Exception:
            pass
        log.error("자동화 실패(%s): %s", action, exc)
        raise
    finally:
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()


# ─────────────────────────────────────────────────────────────
# CLI 단독 테스트: python -m src.automation checkin | checkout
# ─────────────────────────────────────────────────────────────
def _main() -> None:
    valid = {"login", "checkin", "checkout", "checkin-test", "checkout-test"}
    arg = sys.argv[1] if len(sys.argv) > 1 else "login"
    if arg not in valid:
        print("사용법: python -m src.automation [login|checkin|checkout|checkin-test|checkout-test]")
        print("  login         : 로그인까지만 검증 (출퇴근 클릭 안 함, 안전)")
        print("  checkin       : 실제 출근 처리 (모달 '확인')")
        print("  checkout      : 실제 퇴근 처리 (모달 '확인')")
        print("  checkin-test  : 출근 버튼→모달까지만, '취소'로 마무리 (안전)")
        print("  checkout-test : 퇴근 버튼→모달까지만, '취소'로 마무리 (안전)")
        raise SystemExit(2)

    login_only = arg == "login"
    confirm = not arg.endswith("-test")
    action = "checkin" if login_only else arg.replace("-test", "")
    result = asyncio.run(
        run_action(action, login_only=login_only, confirm=confirm)
    )
    print(f"완료 — 스크린샷: {result.screenshot}")


if __name__ == "__main__":
    _main()
