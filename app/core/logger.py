
# logger.py
# app.core.logger


import sys
import io
import logging
from loguru import logger
from app.core.paths import LOGS_DIR


class InterceptHandler(logging.Handler):
    """Перехватчик стандартных логов Python в loguru"""
    
    def emit(self, record):
        # Получить соответствующий уровень loguru
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # Найти источник вызова
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


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
    
    # Перехватить логи schwab библиотеки и направить в loguru
    # Это перенаправит сообщения типа "The refresh token will expire soon!"
    for logger_name in ["schwab", "schwab.auth", "schwab.client", "httpx"]:
        py_logger = logging.getLogger(logger_name)
        py_logger.setLevel(logging.WARNING)
        py_logger.handlers = [InterceptHandler()]  # Заменить все handlers
        py_logger.propagate = False  # Не передавать родителю

    # Функция для выравнивания source
    def format_source(record):
        source = f"{record['module']}:{record['function']}:{record['line']}"
        record["extra"]["source"] = f"{source: <53}"
    
    # Формат с выровненным source
    aligned_format = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[source]} | {message}"

    # Вывод в консоль (опционально - замедляет GUI)
    if console:
        # Формат с выравниванием и цветом (как в файле, но с цветами)
        color_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{extra[source]}</cyan> "
            "| <level>{message}</level>"
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
            filter=lambda record: format_source(record) or True,
        )

    # ═══════════════════════════════════════════════════════════════
    # 1. ГЛАВНЫЙ ЛОГ - всё (переименован из schwab_client.log)
    # ═══════════════════════════════════════════════════════════════
    main_log_file = LOGS_DIR / "app_schwab.log"
    logger.add(
        main_log_file,
        level=level.upper(),
        rotation="1 week",
        retention=4,  # Хранить только 4 zip файла
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