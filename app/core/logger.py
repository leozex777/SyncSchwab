
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

    # Функция для выравнивания source
    def format_source(record):
        source = f"{record['module']}:{record['function']}:{record['line']}"
        record["extra"]["source"] = f"{source: <50}"
    
    # Формат с выровненным source
    aligned_format = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[source]} | {message}"

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

    # ═══════════════════════════════════════════════════════════════
    # 1. ГЛАВНЫЙ ЛОГ - всё (переименован из schwab_client.log)
    # ═══════════════════════════════════════════════════════════════
    main_log_file = LOGS_DIR / "app_schwab.log"
    logger.add(
        main_log_file,
        level=level.upper(),
        rotation="1 week",
        retention="4 weeks",
        compression="zip",
        format=aligned_format,
        encoding="utf-8",
        filter=lambda record: format_source(record) or True,
    )

    # ═══════════════════════════════════════════════════════════════
    # 2. SYNC LOG - только синхронизация [SYNC]
    # ═══════════════════════════════════════════════════════════════
    sync_log_file = LOGS_DIR / "sync.log"
    
    def sync_filter(record):
        format_source(record)
        return "[SYNC]" in record["message"]
    
    logger.add(
        sync_log_file,
        level="INFO",
        rotation="1 week",
        retention="4 weeks",
        compression="zip",
        format=aligned_format,
        encoding="utf-8",
        filter=sync_filter,
    )

    # ═══════════════════════════════════════════════════════════════
    # 3. ORDERS LOG - только ордера [ORDER]
    # ═══════════════════════════════════════════════════════════════
    orders_log_file = LOGS_DIR / "orders.log"
    
    def orders_filter(record):
        format_source(record)
        return "[ORDER]" in record["message"]
    
    logger.add(
        orders_log_file,
        level="INFO",
        rotation="1 week",
        retention="4 weeks",
        compression="zip",
        format=aligned_format,
        encoding="utf-8",
        filter=orders_filter,
    )

    # ═══════════════════════════════════════════════════════════════
    # 4. ERRORS LOG - только ошибки
    # ═══════════════════════════════════════════════════════════════
    error_file = LOGS_DIR / "errors.log"
    logger.add(
        error_file,
        level="ERROR",
        rotation="1 week",
        retention="4 weeks",
        compression="zip",
        format=aligned_format,
        encoding="utf-8",
        filter=lambda record: format_source(record) or True,
    )


__all__ = ["logger", "setup_logger"]