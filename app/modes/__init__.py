# app/modes/__init__.py
"""
Модули режимов синхронизации.

4 режима:
- simulation: 🔶 SIMULATION - виртуальные ордера с dry cache
- live: 🔴 LIVE - реальные ордера
- monitor_live: 🔍🔴 MONITOR LIVE DELTA - отслеживание без ордеров (реальные данные)
- monitor_simulation: 🔍🔶 MONITOR SIMULATION DELTA - отслеживание без ордеров (dry cache)
"""

from app.modes.base import SyncMode

__all__ = ['SyncMode']
