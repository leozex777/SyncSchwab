
# error_handler.py
# app.core.error_handler

import time
from typing import Callable, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logger import logger
from app.core.json_utils import load_json


class ErrorType(Enum):
    """Типы ошибок API"""
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    BAD_REQUEST = "bad_request"
    ORDER_REJECTED = "order_rejected"
    INVALID_SYMBOL = "invalid_symbol"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Серьёзность ошибки"""
    LOW = "low"            # Можно продолжать
    MEDIUM = "medium"      # Предупреждение
    HIGH = "high"          # Критическая, возможна остановка
    CRITICAL = "critical"  # Требуется остановка


@dataclass
class APIError:
    """Структура ошибки API"""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    code: Optional[str] = None
    symbol: Optional[str] = None
    retryable: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "code": self.code,
            "symbol": self.symbol,
            "retryable": self.retryable,
            "timestamp": self.timestamp
        }


class ErrorClassifier:
    """Классификатор ошибок API"""
    
    @staticmethod
    def classify(exception: Exception, response=None, symbol: str = None) -> APIError:
        """
        Классифицировать ошибку и вернуть структурированный объект.
        
        Args:
            exception: Исключение
            response: HTTP response (если есть)
            symbol: Символ акции (если применимо)
        """
        error_msg = str(exception).lower()
        status_code = getattr(response, 'status_code', None) if response else None
        response_text = getattr(response, 'text', '').lower() if response else ''
        
        # Определить тип ошибки по статус коду
        if status_code:
            return ErrorClassifier._classify_by_status(status_code, response_text, symbol)
        
        # Определить тип ошибки по тексту исключения
        return ErrorClassifier._classify_by_message(error_msg, symbol)
    
    @staticmethod
    def _classify_by_status(status_code: int, response_text: str, symbol: str = None) -> APIError:
        """Классификация по HTTP статус коду"""
        
        if status_code == 401:
            return APIError(
                error_type=ErrorType.UNAUTHORIZED,
                severity=ErrorSeverity.CRITICAL,
                message="Authentication failed. Token may be expired.",
                code=str(status_code),
                symbol=symbol,
                retryable=False  # Нужна повторная авторизация
            )
        
        if status_code == 400:
            # Проверить детали ошибки
            if 'insufficient' in response_text or 'funds' in response_text:
                return APIError(
                    error_type=ErrorType.INSUFFICIENT_FUNDS,
                    severity=ErrorSeverity.MEDIUM,
                    message="Insufficient funds for order",
                    code=str(status_code),
                    symbol=symbol,
                    retryable=False
                )
            if 'invalid' in response_text and 'symbol' in response_text:
                return APIError(
                    error_type=ErrorType.INVALID_SYMBOL,
                    severity=ErrorSeverity.LOW,
                    message=f"Invalid symbol: {symbol}",
                    code=str(status_code),
                    symbol=symbol,
                    retryable=False
                )
            if 'reject' in response_text:
                return APIError(
                    error_type=ErrorType.ORDER_REJECTED,
                    severity=ErrorSeverity.MEDIUM,
                    message="Order rejected by broker",
                    code=str(status_code),
                    symbol=symbol,
                    retryable=False
                )
            return APIError(
                error_type=ErrorType.BAD_REQUEST,
                severity=ErrorSeverity.MEDIUM,
                message=f"Bad request: {response_text[:100]}",
                code=str(status_code),
                symbol=symbol,
                retryable=False
            )
        
        if status_code == 429:
            return APIError(
                error_type=ErrorType.RATE_LIMIT,
                severity=ErrorSeverity.MEDIUM,
                message="Rate limit exceeded. Too many requests.",
                code=str(status_code),
                symbol=symbol,
                retryable=True
            )
        
        if status_code >= 500:
            return APIError(
                error_type=ErrorType.SERVER_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message=f"Server error: {status_code}",
                code=str(status_code),
                symbol=symbol,
                retryable=True
            )
        
        # Неизвестный статус
        return APIError(
            error_type=ErrorType.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            message=f"HTTP error: {status_code}",
            code=str(status_code),
            symbol=symbol,
            retryable=False
        )
    
    @staticmethod
    def _classify_by_message(error_msg: str, symbol: str = None) -> APIError:
        """Классификация по тексту ошибки"""
        
        if 'timeout' in error_msg or 'timed out' in error_msg:
            return APIError(
                error_type=ErrorType.TIMEOUT,
                severity=ErrorSeverity.MEDIUM,
                message="Request timed out",
                symbol=symbol,
                retryable=True
            )
        
        if 'connection' in error_msg or 'network' in error_msg:
            return APIError(
                error_type=ErrorType.NETWORK_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message="Network connection error",
                symbol=symbol,
                retryable=True
            )
        
        if 'unauthorized' in error_msg or 'auth' in error_msg:
            return APIError(
                error_type=ErrorType.UNAUTHORIZED,
                severity=ErrorSeverity.CRITICAL,
                message="Authentication error",
                symbol=symbol,
                retryable=False
            )
        
        if 'insufficient' in error_msg or 'funds' in error_msg:
            return APIError(
                error_type=ErrorType.INSUFFICIENT_FUNDS,
                severity=ErrorSeverity.MEDIUM,
                message="Insufficient funds",
                symbol=symbol,
                retryable=False
            )
        
        if 'reject' in error_msg:
            return APIError(
                error_type=ErrorType.ORDER_REJECTED,
                severity=ErrorSeverity.MEDIUM,
                message="Order rejected",
                symbol=symbol,
                retryable=False
            )
        
        # Неизвестная ошибка
        return APIError(
            error_type=ErrorType.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            message=error_msg[:200],
            symbol=symbol,
            retryable=False
        )


class RetryHandler:
    """Обработчик повторных попыток"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        """
        Args:
            max_retries: Максимальное количество повторов
            base_delay: Базовая задержка между попытками (секунды)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    def execute_with_retry(
        self,
        func: Callable,
        *args,
        symbol: str = None,
        **kwargs
    ) -> Tuple[Any, Optional[APIError]]:
        """
        Выполнить функцию с повторными попытками.
        
        Args:
            func: Функция для выполнения
            symbol: Символ (для логирования)
            *args, **kwargs: Аргументы функции
            
        Returns:
            (result, error) - результат и ошибка (если есть)
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return result, None
                
            except Exception as e:
                # Классифицировать ошибку
                api_error = ErrorClassifier.classify(e, symbol=symbol)
                last_error = api_error
                
                # Логировать
                if attempt < self.max_retries and api_error.retryable:
                    delay = self.base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"⚠️ Attempt {attempt + 1}/{self.max_retries + 1} failed for {symbol}: "
                        f"{api_error.message}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    if not api_error.retryable:
                        logger.error(f"❌ Non-retryable error for {symbol}: {api_error.message}")
                    else:
                        logger.error(f"❌ All {self.max_retries + 1} attempts failed for {symbol}")
                    break
        
        return None, last_error


class ErrorTracker:
    """Отслеживание ошибок за сессию"""
    
    def __init__(self, max_errors: int = 5):
        """
        Args:
            max_errors: Максимальное количество ошибок до критического состояния
        """
        self.max_errors = max_errors
        self.errors: list = []
        self.consecutive_errors = 0
        self._critical = False
    
    def add_error(self, error: APIError):
        """Добавить ошибку"""
        self.errors.append(error)
        self.consecutive_errors += 1
        
        # Проверить критическое состояние
        if error.severity == ErrorSeverity.CRITICAL:
            self._critical = True
            logger.error(f"🛑 Critical error detected: {error.message}")
        
        if len(self.errors) >= self.max_errors:
            logger.warning(f"⚠️ Too many errors ({len(self.errors)}) in session")
    
    def add_success(self):
        """Сбросить счётчик последовательных ошибок при успехе"""
        self.consecutive_errors = 0
    
    def is_critical(self) -> bool:
        """Проверить критическое состояние"""
        return self._critical
    
    def should_stop(self, stop_on_critical: bool = False) -> bool:
        """
        Проверить нужно ли остановить синхронизацию.
        
        Args:
            stop_on_critical: Настройка из конфига
        """
        if not stop_on_critical:
            return False
        
        # Остановить при критической ошибке
        if self._critical:
            return True
        
        # Остановить при 3+ последовательных ошибках
        if self.consecutive_errors >= 3:
            logger.warning("⚠️ 3+ consecutive errors, recommending stop")
            return True
        
        return False
    
    def get_summary(self) -> dict:
        """Получить сводку ошибок"""
        return {
            "total_errors": len(self.errors),
            "consecutive_errors": self.consecutive_errors,
            "is_critical": self._critical,
            "error_types": [e.error_type.value for e in self.errors]
        }
    
    def reset(self):
        """Сбросить трекер"""
        self.errors = []
        self.consecutive_errors = 0
        self._critical = False


def get_error_settings() -> dict:
    """Получить настройки обработки ошибок из конфига"""
    settings = load_json("config/general_settings.json", default={})
    
    return {
        "retry_count": settings.get("error_handling", {}).get("retry_count", 3),
        "sound_on_error": settings.get("error_handling", {}).get("sound_on_error", False),
        "stop_on_critical": settings.get("error_handling", {}).get("stop_on_critical", False),
        "max_errors_per_session": settings.get("error_handling", {}).get("max_errors_per_session", 5)
    }
