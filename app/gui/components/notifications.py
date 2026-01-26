
# notifications.py
# app.gui.components.notifications

"""
Компонент для показа Toast уведомлений в GUI.

Использование:
    В любой странице добавить:
    
    from app.gui.components.notifications import render_notifications
    render_notifications()
"""

import streamlit as st
from app.core.notification_service import get_notification_service


def render_notifications():
    """
    Отрисовать fragment для показа Toast уведомлений.
    Вызывать один раз на странице.
    """
    _notification_fragment()


@st.fragment(run_every=2)
def _notification_fragment():
    """
    Fragment который проверяет:
    1. Очередь уведомлений каждые 2 секунды
    2. Флаг обновления кэша → st.rerun() для обновления таблиц
    """
    from app.core.cache_manager import check_cache_updated, refresh_cache_from_file
    
    # Проверить обновление кэша (для Auto Sync)
    if check_cache_updated():
        refresh_cache_from_file()
        # scope="app" перезапускает ВСЁ приложение, не только fragment
        st.rerun(scope="app")
    
    # Показать уведомления
    service = get_notification_service()
    notifications = service.get_pending(limit=5)
    
    for notif in notifications:
        # Определить иконку
        icon_map = {
            'success': '✅',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️'
        }
        icon = icon_map.get(notif.type, 'ℹ️')
        
        # Показать toast
        st.toast(f"{icon} {notif.message}")


def show_toast(message: str, notification_type: str = "info"):
    """
    Добавить уведомление в очередь для показа.
    
    Args:
        message: Текст сообщения
        notification_type: Тип (success, error, warning, info)
    """
    service = get_notification_service()
    
    if notification_type == "success":
        service.success(message)
    elif notification_type == "error":
        service.error(message)
    elif notification_type == "warning":
        service.warning(message)
    else:
        service.info(message)


# ════════════════════════════════════════════════════════════════
# QUICK HELPERS
# ════════════════════════════════════════════════════════════════

def toast_success(message: str):
    """Показать success toast"""
    show_toast(message, "success")


def toast_error(message: str):
    """Показать error toast"""
    show_toast(message, "error")


def toast_warning(message: str):
    """Показать warning toast"""
    show_toast(message, "warning")


def toast_info(message: str):
    """Показать info toast"""
    show_toast(message, "info")
