
# worker_client.py
# app.core.worker_client
#
# Модуль для управления Sync Worker из GUI.
# Worker работает как отдельный процесс, общение через файлы.

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from pathlib import Path

from app.core.json_utils import load_json, save_json
from app.core.paths import CONFIG_DIR
from app.core.logger import logger

# Файл статуса worker
WORKER_STATUS_FILE = CONFIG_DIR / "worker_status.json"

# Таймаут для определения что worker "мёртв"
HEARTBEAT_TIMEOUT_SECONDS = 120  # 2 минуты без heartbeat = worker не отвечает


def get_default_status() -> Dict:
    """Получить статус по умолчанию"""
    return {
        "command": "stop",
        "running": False,
        "started_at": None,
        "last_heartbeat": None,
        "last_sync": None,
        "last_sync_result": None,
        "interval_seconds": 60,
        "pid": None,
        "error": None
    }


def get_worker_status() -> Dict:
    """
    Получить полный статус worker.
    
    Returns:
        Dict со статусом worker
    """
    return load_json(WORKER_STATUS_FILE, default=get_default_status())


def is_worker_alive() -> Tuple[bool, str]:
    """
    Проверить жив ли worker (по heartbeat).
    
    Returns:
        (is_alive: bool, message: str)
    """
    status = get_worker_status()
    
    # Если команда stop — worker должен быть остановлен
    if status.get("command") == "stop":
        return False, "Stopped"
    
    # Проверяем heartbeat
    last_heartbeat = status.get("last_heartbeat")
    
    if not last_heartbeat:
        return False, "No heartbeat yet"
    
    try:
        heartbeat_time = datetime.fromisoformat(last_heartbeat)
        elapsed = (datetime.now() - heartbeat_time).total_seconds()
        
        if elapsed > HEARTBEAT_TIMEOUT_SECONDS:
            return False, f"No response for {int(elapsed)}s"
        
        return True, f"Active ({int(elapsed)}s ago)"
    except Exception as e:
        return False, f"Error: {e}"


def is_worker_running() -> bool:
    """
    Проверить работает ли worker.
    
    Returns:
        True если worker работает и отвечает
    """
    status = get_worker_status()
    
    # Команда должна быть start
    if status.get("command") != "start":
        return False
    
    # И worker должен быть жив
    is_alive, _ = is_worker_alive()
    return is_alive


def start_worker() -> bool:
    """
    Запустить worker (отправить команду start).
    
    Returns:
        True если команда отправлена успешно
    """
    try:
        status = get_worker_status()
        status["command"] = "start"
        save_json(WORKER_STATUS_FILE, status)
        logger.info("[WORKER CLIENT] Start command sent")
        return True
    except Exception as e:
        logger.error(f"[WORKER CLIENT] Failed to send start command: {e}")
        return False


def stop_worker() -> bool:
    """
    Остановить worker (отправить команду stop).
    
    Returns:
        True если команда отправлена успешно
    """
    try:
        status = get_worker_status()
        status["command"] = "stop"
        save_json(WORKER_STATUS_FILE, status)
        logger.info("[WORKER CLIENT] Stop command sent")
        return True
    except Exception as e:
        logger.error(f"[WORKER CLIENT] Failed to send stop command: {e}")
        return False


def get_worker_info() -> Dict:
    """
    Получить информацию о worker для отображения в GUI.
    
    Returns:
        Dict с информацией:
        - is_running: bool
        - status_text: str
        - status_color: str (green/yellow/red)
        - last_sync: str
        - last_sync_result: str
        - uptime: str
    """
    status = get_worker_status()
    is_alive, alive_message = is_worker_alive()
    
    info = {
        "is_running": False,
        "status_text": "Stopped",
        "status_color": "gray",
        "last_sync": None,
        "last_sync_result": None,
        "uptime": None,
        "pid": status.get("pid"),
        "error": status.get("error")
    }
    
    command = status.get("command", "stop")
    
    if command == "stop":
        info["status_text"] = "Stopped"
        info["status_color"] = "gray"
    elif command == "start":
        if is_alive:
            info["is_running"] = True
            info["status_text"] = f"Running ({alive_message})"
            info["status_color"] = "green"
        else:
            info["status_text"] = f"Not responding: {alive_message}"
            info["status_color"] = "red"
    
    # Last sync
    last_sync = status.get("last_sync")
    if last_sync:
        try:
            sync_time = datetime.fromisoformat(last_sync)
            elapsed = (datetime.now() - sync_time).total_seconds()
            if elapsed < 60:
                info["last_sync"] = f"{int(elapsed)}s ago"
            elif elapsed < 3600:
                info["last_sync"] = f"{int(elapsed/60)}m ago"
            else:
                info["last_sync"] = f"{int(elapsed/3600)}h ago"
        except:
            info["last_sync"] = last_sync
    
    info["last_sync_result"] = status.get("last_sync_result")
    
    # Uptime
    started_at = status.get("started_at")
    if started_at and info["is_running"]:
        try:
            start_time = datetime.fromisoformat(started_at)
            uptime = datetime.now() - start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            if hours > 0:
                info["uptime"] = f"{hours}h {minutes}m"
            else:
                info["uptime"] = f"{minutes}m"
        except:
            pass
    
    return info


def format_worker_status_for_display() -> Tuple[str, str]:
    """
    Форматировать статус worker для отображения в sidebar.
    
    Returns:
        (status_text, emoji)
    """
    info = get_worker_info()
    
    if info["is_running"]:
        uptime = info.get("uptime", "")
        if uptime:
            return f"Worker: {uptime}", "🟢"
        return "Worker: Running", "🟢"
    elif info["status_color"] == "red":
        return "Worker: Not responding!", "🔴"
    else:
        return "Worker: Stopped", "⚪"
