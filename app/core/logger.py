
# logger.py
# app.core.logger


import sys
import io
from loguru import logger
from app.core.paths import LOGS_DIR


def setup_logger(level: str = "INFO", console: bool = False) -> None:
    """
    Настройка логера.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        console: Выводить в консоль (замедляет GUI)
    """
    logger.remove()

    # Создаём папку logs/
    LOGS_DIR.mkdir(exist_ok=True)

    # Вывод в консоль (опционально - замедляет GUI)
    if console:
        color_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        )

        # Исправление кодировки для Windows консоли
        if sys.platform == 'win32':
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

        logger.add(
            sys.stderr,
            level=level.upper(),
            format=color_format,
            backtrace=True,
            diagnose=False,
            colorize=True,
        )

    # Вывод в файл (всегда)
    log_file = LOGS_DIR / "schwab_client.log"
    logger.add(
        log_file,
        level=level.upper(),
        rotation="1 week",
        retention="4 weeks",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}:{function}:{line} | {message}",
        encoding="utf-8",  # Явно указываем кодировку
    )

    # Отдельный файл для ошибок
    error_file = LOGS_DIR / "errors.log"
    logger.add(
        error_file,
        level="ERROR",
        rotation="1 week",
        retention="4 weeks",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}:{function}:{line} | {message}",
        encoding="utf-8",  # Явно указываем кодировку
    )


__all__ = ["logger", "setup_logger"]