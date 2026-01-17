# app/modes/simulation/__init__.py
"""
🔶 SIMULATION MODE - Виртуальные ордера с dry cache.

Файлы:
- sync.py: SimulationSync класс
- cache_dry.py: Управление account_cache_dry.json
- history_dry.py: Управление *_history_dry.json
"""

from app.modes.simulation.sync import SimulationSync

__all__ = ['SimulationSync']
