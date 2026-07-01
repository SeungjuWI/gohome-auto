"""로깅 설정.

파일(logs/automation.log) + 콘솔로 동시에 출력한다.
비밀값이 로그에 남지 않도록 마스킹 헬퍼를 제공한다.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "automation.log"

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """루트 로거에 파일 + 콘솔 핸들러를 1회만 등록한다."""
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """setup_logging()이 아직이면 자동 초기화 후 로거 반환."""
    if not _configured:
        setup_logging()
    return logging.getLogger(name)


def mask_secret(value: str, keep: int = 2) -> str:
    """비밀값 마스킹 — 앞 `keep`글자만 남긴다. 로그 출력 전 사용."""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)


if __name__ == "__main__":
    setup_logging()
    log = get_logger("logger.selftest")
    log.info("로깅 설정 정상 — 파일: %s", LOG_FILE)
    log.info("마스킹 예시 token=%s", mask_secret("1234567890"))
