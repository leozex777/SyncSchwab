
# __init__.py
# app.gui.components.__init__


from . import (
    sidebar,
    dashboard,  # ← ДОБАВЛЕНО
    main_account,
    client_management,
    client_details,
    synchronization,
    modals
)

__all__ = [
    'sidebar',
    'dashboard',  # ← ДОБАВЛЕНО
    'main_account',
    'client_management',
    'client_details',
    'synchronization',
    'modals'
]