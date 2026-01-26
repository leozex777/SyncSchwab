# config_cache.py
# app.core.config_cache

"""
Кэширование конфигурационных файлов в session_state.

Кэшируются:
- config/general_settings.json
- config/clients.json
- config/ui_state.json
- data/clients/{client_id}_history.json (только LIVE)

НЕ кэшируются:
- *_history_dry.json (используется редко)
- tokens/*.json (меняются автоматически)
"""

from typing import Dict, List
import os
from app.core.json_utils import load_json, save_json
from app.core.logger import logger


def _has_streamlit_context() -> bool:
    """Проверить есть ли Streamlit контекст"""
    # Worker mode - сразу возвращаем False без проверки streamlit
    if os.environ.get('SYNC_WORKER_MODE'):
        return False
    
    try:
        import importlib
        scriptrunner = importlib.import_module('streamlit.runtime.scriptrunner')
        ctx_func = getattr(scriptrunner, 'get_script_run_ctx', None)
        return ctx_func() is not None if ctx_func else False
    except (ImportError, AttributeError):
        return False


class _LazyStreamlit:
    """
    Ленивый импорт streamlit — загружается только при первом обращении
    и только если есть Streamlit контекст (не в Worker).
    """
    _st = None
    _checked = False
    _has_context = False
    
    @property
    def session_state(self):
        if not self._checked:
            self._checked = True
            self._has_context = _has_streamlit_context()
        
        if not self._has_context:
            # Worker mode - вернуть пустой dict-like объект
            return _DummySessionState()
        
        if self._st is None:
            import streamlit
            self._st = streamlit
        return self._st.session_state


class _DummySessionState(dict):
    """Заглушка для session_state в Worker режиме"""
    def __contains__(self, key):
        return False
    
    def __getitem__(self, key):
        return {}  # Возвращаем пустой dict вместо None
    
    def __setitem__(self, key, value):
        pass  # Игнорируем запись
    
    def get(self, key, default=None):
        return default  # Возвращаем default
    
    def keys(self):
        return []


# Глобальный объект для ленивого доступа к streamlit
st = _LazyStreamlit()


class ConfigCache:
    """Кэш конфигурационных файлов в session_state"""
    
    # ═══════════════════════════════════════════════════════════════
    # КЛЮЧИ КЭША
    # ═══════════════════════════════════════════════════════════════
    
    _KEY_GENERAL_SETTINGS = '_cache_general_settings'
    _KEY_CLIENTS = '_cache_clients'
    _KEY_UI_STATE = '_cache_ui_state'
    _KEY_HISTORY_PREFIX = '_cache_history_'
    
    # ═══════════════════════════════════════════════════════════════
    # GENERAL SETTINGS
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def get_general_settings() -> Dict:
        """
        Получить general_settings из кэша или загрузить из файла.
        
        Returns:
            Dict с настройками
        """
        if ConfigCache._KEY_GENERAL_SETTINGS not in st.session_state:
            logger.debug("[CACHE] Loading general_settings from file")
            st.session_state[ConfigCache._KEY_GENERAL_SETTINGS] = load_json(
                "config/general_settings.json", 
                default={}
            )
        return st.session_state[ConfigCache._KEY_GENERAL_SETTINGS]
    
    @staticmethod
    def reload_general_settings() -> Dict:
        """
        Перезагрузить general_settings из файла (после Save).
        
        Returns:
            Dict с настройками
        """
        logger.debug("[CACHE] Reloading general_settings from file")
        st.session_state[ConfigCache._KEY_GENERAL_SETTINGS] = load_json(
            "config/general_settings.json", 
            default={}
        )
        return st.session_state[ConfigCache._KEY_GENERAL_SETTINGS]
    
    @staticmethod
    def save_general_settings(data: Dict) -> None:
        """
        Сохранить general_settings в файл и обновить кэш.
        
        Args:
            data: Dict с настройками
        """
        save_json("config/general_settings.json", data)
        st.session_state[ConfigCache._KEY_GENERAL_SETTINGS] = data
        logger.debug("[CACHE] Saved and cached general_settings")
    
    # ═══════════════════════════════════════════════════════════════
    # CLIENTS
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def get_clients() -> List[Dict]:
        """
        Получить clients из кэша или загрузить из файла.
        
        Returns:
            List с клиентами
        """
        if ConfigCache._KEY_CLIENTS not in st.session_state:
            logger.debug("[CACHE] Loading clients from file")
            st.session_state[ConfigCache._KEY_CLIENTS] = load_json(
                "config/clients.json", 
                default=[]
            )
        return st.session_state[ConfigCache._KEY_CLIENTS]
    
    @staticmethod
    def reload_clients() -> List[Dict]:
        """
        Перезагрузить clients из файла (после Save).
        
        Returns:
            List с клиентами
        """
        logger.debug("[CACHE] Reloading clients from file")
        st.session_state[ConfigCache._KEY_CLIENTS] = load_json(
            "config/clients.json", 
            default=[]
        )
        return st.session_state[ConfigCache._KEY_CLIENTS]
    
    @staticmethod
    def save_clients(data: List[Dict]) -> None:
        """
        Сохранить clients в файл и обновить кэш.
        
        Args:
            data: List с клиентами
        """
        save_json("config/clients.json", data)
        st.session_state[ConfigCache._KEY_CLIENTS] = data
        logger.debug("[CACHE] Saved and cached clients")
    
    # ═══════════════════════════════════════════════════════════════
    # UI STATE
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def get_ui_state() -> Dict:
        """
        Получить ui_state из кэша или загрузить из файла.
        
        Returns:
            Dict с состоянием UI
        """
        if ConfigCache._KEY_UI_STATE not in st.session_state:
            logger.debug("[CACHE] Loading ui_state from file")
            st.session_state[ConfigCache._KEY_UI_STATE] = load_json(
                "config/ui_state.json", 
                default={}
            )
        return st.session_state[ConfigCache._KEY_UI_STATE]
    
    @staticmethod
    def reload_ui_state() -> Dict:
        """
        Перезагрузить ui_state из файла (после Save).
        
        Returns:
            Dict с состоянием UI
        """
        logger.debug("[CACHE] Reloading ui_state from file")
        st.session_state[ConfigCache._KEY_UI_STATE] = load_json(
            "config/ui_state.json", 
            default={}
        )
        return st.session_state[ConfigCache._KEY_UI_STATE]
    
    @staticmethod
    def save_ui_state(data: Dict) -> None:
        """
        Сохранить ui_state в файл и обновить кэш.
        
        Args:
            data: Dict с состоянием UI
        """
        save_json("config/ui_state.json", data)
        st.session_state[ConfigCache._KEY_UI_STATE] = data
        logger.debug("[CACHE] Saved and cached ui_state")
    
    # ═══════════════════════════════════════════════════════════════
    # HISTORY (только LIVE, не dry)
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def _get_history_key(client_id: str) -> str:
        """Получить ключ кэша для истории клиента"""
        return f"{ConfigCache._KEY_HISTORY_PREFIX}{client_id}"
    
    @staticmethod
    def _get_history_file(client_id: str) -> str:
        """Получить путь к файлу истории клиента (только LIVE)"""
        return f"data/clients/{client_id}_history.json"
    
    @staticmethod
    def get_history(client_id: str) -> List[Dict]:
        """
        Получить history из кэша или загрузить из файла.
        Кэшируется только LIVE history (не dry).
        
        Args:
            client_id: ID клиента
            
        Returns:
            List с историей синхронизаций
        """
        cache_key = ConfigCache._get_history_key(client_id)
        
        if cache_key not in st.session_state:
            history_file = ConfigCache._get_history_file(client_id)
            logger.debug(f"[CACHE] Loading history for {client_id} from file")
            st.session_state[cache_key] = load_json(history_file, default=[])
        
        return st.session_state[cache_key]
    
    @staticmethod
    def reload_history(client_id: str) -> List[Dict]:
        """
        Перезагрузить history из файла (после записи).
        
        Args:
            client_id: ID клиента
            
        Returns:
            List с историей синхронизаций
        """
        cache_key = ConfigCache._get_history_key(client_id)
        history_file = ConfigCache._get_history_file(client_id)
        
        logger.debug(f"[CACHE] Reloading history for {client_id} from file")
        st.session_state[cache_key] = load_json(history_file, default=[])
        
        return st.session_state[cache_key]
    
    @staticmethod
    def update_history(client_id: str, data: List[Dict]) -> None:
        """
        Обновить кэш истории после записи в файл.
        (Файл записывается в synchronizer.py, здесь только обновляем кэш)
        
        Args:
            client_id: ID клиента
            data: List с историей
        """
        # Пропустить если нет Streamlit контекста (Worker)
        if not _has_streamlit_context():
            return
        
        cache_key = ConfigCache._get_history_key(client_id)
        st.session_state[cache_key] = data
        logger.debug(f"[CACHE] Updated history cache for {client_id}")
    
    # ═══════════════════════════════════════════════════════════════
    # CLEAR CACHE
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def clear_all() -> None:
        """Очистить весь кэш конфигов"""
        keys_to_remove = [
            ConfigCache._KEY_GENERAL_SETTINGS,
            ConfigCache._KEY_CLIENTS,
            ConfigCache._KEY_UI_STATE,
        ]
        
        # Удалить history кэши
        for key in list(st.session_state.keys()):
            if key.startswith(ConfigCache._KEY_HISTORY_PREFIX):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            if key in st.session_state:
                del st.session_state[key]
        
        logger.debug("[CACHE] Cleared all config cache")


# ═══════════════════════════════════════════════════════════════
# УДОБНЫЕ ФУНКЦИИ (алиасы)
# ═══════════════════════════════════════════════════════════════

def get_general_settings() -> Dict:
    """Алиас для ConfigCache.get_general_settings()"""
    return ConfigCache.get_general_settings()


def get_clients_config() -> List[Dict]:
    """Алиас для ConfigCache.get_clients()"""
    return ConfigCache.get_clients()


def get_ui_state() -> Dict:
    """Алиас для ConfigCache.get_ui_state()"""
    return ConfigCache.get_ui_state()


def get_client_history(client_id: str) -> List[Dict]:
    """Алиас для ConfigCache.get_history()"""
    return ConfigCache.get_history(client_id)


# ═══════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ WORKER (без session_state)
# ═══════════════════════════════════════════════════════════════

def get_clients_from_file() -> Dict:
    """
    Получить clients напрямую из файла (для Worker).
    Не использует session_state.
    
    Returns:
        Dict с клиентами
    """
    return load_json("config/clients.json", default={})


def get_general_settings_from_file() -> Dict:
    """
    Получить general_settings напрямую из файла (для Worker).
    Не использует session_state.
    
    Returns:
        Dict с настройками
    """
    return load_json("config/general_settings.json", default={})
