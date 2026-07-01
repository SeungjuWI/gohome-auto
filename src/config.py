"""환경변수(.env) 로드 및 검증.

모든 비밀값·설정은 이 모듈을 통해서만 접근한다.
필수값이 비어 있으면 즉시 명확한 에러를 던져, 실행 도중이 아니라
시작 시점에 문제를 발견하도록 한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트(.env 위치) = 이 파일의 두 단계 상위
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# .env 로드 (이미 설정된 실제 환경변수는 덮어쓰지 않음)
load_dotenv(dotenv_path=ENV_PATH)


class ConfigError(RuntimeError):
    """필수 환경변수 누락 등 설정 오류."""


def _require(key: str) -> str:
    """필수 문자열 환경변수. 없거나 비어 있으면 ConfigError."""
    value = os.getenv(key, "").strip()
    if not value:
        raise ConfigError(
            f"필수 환경변수 '{key}'가 비어 있습니다. .env 파일을 확인하세요 "
            f"(참고 템플릿: .env.example)."
        )
    return value


def _get_str(key: str, default: str) -> str:
    value = os.getenv(key, "").strip()
    return value or default


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"환경변수 '{key}'는 정수여야 합니다 (현재 값: {raw!r}).") from exc


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Config:
    """실행에 필요한 모든 설정값의 스냅샷."""

    # 그룹웨어 로그인 (2단계 로그인)
    company_code: str
    user_id: str
    user_pw: str
    gw_url: str
    gw_login_url: str

    # 텔레그램
    telegram_bot_token: str
    telegram_chat_id: int

    # 동작 설정
    headless: bool
    default_timeout_ms: int
    max_retries: int

    def masked(self) -> dict[str, str]:
        """로그 출력용 — 비밀값을 마스킹한 표현."""
        return {
            "company_code": self.company_code,
            "user_id": _mask(self.user_id),
            "user_pw": "********",
            "gw_url": self.gw_url,
            "gw_login_url": self.gw_login_url,
            "telegram_bot_token": _mask(self.telegram_bot_token),
            "telegram_chat_id": str(self.telegram_chat_id),
            "headless": str(self.headless),
            "default_timeout_ms": str(self.default_timeout_ms),
            "max_retries": str(self.max_retries),
        }


def _mask(value: str) -> str:
    """앞 2글자만 남기고 마스킹."""
    if len(value) <= 2:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 2)


def load_config() -> Config:
    """.env를 읽어 검증된 Config를 반환한다."""
    chat_id_raw = _require("TELEGRAM_CHAT_ID")
    try:
        chat_id = int(chat_id_raw)
    except ValueError as exc:
        raise ConfigError(
            f"TELEGRAM_CHAT_ID는 숫자여야 합니다 (현재 값: {chat_id_raw!r})."
        ) from exc

    return Config(
        company_code=_require("COMPANY_CODE"),
        user_id=_require("USER_ID"),
        user_pw=_require("USER_PW"),
        gw_url=_get_str("GW_URL", "https://gw.likelion.net/#/"),
        gw_login_url=_get_str(
            "GW_LOGIN_URL", "https://gw.likelion.net/#/login?logout=Y&lang=kr"
        ),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=chat_id,
        headless=_get_bool("HEADLESS", True),
        default_timeout_ms=_get_int("DEFAULT_TIMEOUT_MS", 15000),
        max_retries=_get_int("MAX_RETRIES", 3),
    )


if __name__ == "__main__":
    # 단독 실행 시 설정 로드가 정상인지 빠르게 점검 (비밀값은 마스킹 출력)
    cfg = load_config()
    print("설정 로드 성공:")
    for key, val in cfg.masked().items():
        print(f"  {key} = {val}")
