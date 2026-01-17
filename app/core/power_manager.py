# power_manager.py
# app.core.power_manager

"""
Управление режимом сна Windows.

Предотвращает засыпание компьютера когда работает GUI или Worker.
Экран может гаснуть (это нормально), но компьютер не заснёт.

Usage в GUI (app_streamlit_multi.py):
    from app.core.power_manager import prevent_sleep_gui
    prevent_sleep_gui()  # Вызвать один раз при старте
"""

import sys
import ctypes
import atexit

# Windows API константы
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002  # Не используем - экран может гаснуть
ES_AWAYMODE_REQUIRED = 0x00000040

# Состояние
_sleep_prevented = False


def prevent_sleep() -> bool:
    """
    Запретить компьютеру засыпать.
    Экран может гаснуть, но система не заснёт.
    
    Returns:
        True если успешно, False если ошибка или не Windows
    """
    global _sleep_prevented
    
    if sys.platform != 'win32':
        return False
    
    if _sleep_prevented:
        return True  # Уже активно
    
    try:
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        # - ES_CONTINUOUS: действует до явной отмены
        # - ES_SYSTEM_REQUIRED: предотвращает сон системы
        # noinspection PyUnresolvedReferences
        kernel32 = ctypes.windll.kernel32
        # noinspection PyUnresolvedReferences
        result = kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
        if result:
            _sleep_prevented = True
            return True
        return False
    except (OSError, AttributeError):
        return False


def allow_sleep() -> bool:
    """
    Разрешить компьютеру засыпать.
    
    Returns:
        True если успешно
    """
    global _sleep_prevented
    
    if sys.platform != 'win32':
        return False
    
    try:
        # noinspection PyUnresolvedReferences
        kernel32 = ctypes.windll.kernel32
        # noinspection PyUnresolvedReferences
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        _sleep_prevented = False
        return True
    except (OSError, AttributeError):
        return False


def is_sleep_prevented() -> bool:
    """Проверить активен ли режим предотвращения сна"""
    return _sleep_prevented


# ═══════════════════════════════════════════════════════════════
# GUI INTEGRATION
# ═══════════════════════════════════════════════════════════════

_gui_initialized = False


def prevent_sleep_gui() -> bool:
    """
    Инициализировать предотвращение сна для GUI.
    Вызывать один раз при старте Streamlit приложения.
    
    Автоматически регистрирует cleanup при выходе.
    
    Returns:
        True если успешно
    """
    global _gui_initialized
    
    if _gui_initialized:
        return True
    
    if prevent_sleep():
        # Зарегистрировать cleanup при выходе
        atexit.register(allow_sleep)
        _gui_initialized = True
        return True
    
    return False


# ═══════════════════════════════════════════════════════════════
# WINDOWS UPDATE NOTES
# ═══════════════════════════════════════════════════════════════
#
# Программно заблокировать Windows Update сложно и не рекомендуется.
# 
# Рекомендации для пользователя:
# 
# 1. Настроить Active Hours:
#    Settings → Windows Update → Advanced options → Active hours
#    Установить часы когда программа обычно работает (например 6:00-23:00)
#
# 2. Приостановить обновления на время:
#    Settings → Windows Update → Pause updates for 1 week
#
# 3. Для Pro/Enterprise версий - Group Policy:
#    gpedit.msc → Computer Configuration → Administrative Templates
#    → Windows Components → Windows Update
#    → Configure Automatic Updates → Disabled
