# SyncSchwab - Position Copier

## 📋 Overview

SyncSchwab is a position copying system for Charles Schwab brokerage accounts. It synchronizes positions from a Main Account to multiple Slave (client) accounts automatically.

## 🚀 Features

- **Multi-client support** - Copy positions to multiple accounts simultaneously
- **Three operating modes:**
  - 🧪 **Dry Run** - Quick test without real orders
  - 🔶 **Simulation** - Full test with detailed logs, no real orders
  - 🔴 **Live** - Real trading with actual orders
- **Auto Sync** - Automatic synchronization at configurable intervals
  - **State persistence** - Auto Sync survives browser close/reopen
  - **Background operation** - Continues running when browser is closed
- **Manual Sync** - On-demand synchronization
- **Margin support** - Configure margin usage per client
- **Toast notifications** - Real-time notifications for errors/success
- **Sound alerts** - Audio notification on errors
- **Log Viewer** - Built-in log viewer with filtering and auto-refresh
- **Market Calendar** - Automatic market hours detection (holidays, weekends)
- **Telegram integration** - (Coming soon) Send notifications to Telegram

## 📁 Project Structure

```
SyncSchwab/
├── app/
│   ├── core/
│   │   ├── config.py              # API configuration
│   │   ├── config_cache.py        # Configuration caching
│   │   ├── logger.py              # Logging setup (1-week rotation)
│   │   ├── json_utils.py          # JSON utilities
│   │   ├── sync_service.py        # Synchronization service (singleton)
│   │   ├── scheduler.py           # Event scheduler (heap-based)
│   │   ├── cache_manager.py       # Background cache updates
│   │   ├── error_handler.py       # Error handling & retry logic
│   │   ├── notification_service.py # Toast notifications
│   │   └── market_calendar.py     # Market hours & holidays
│   ├── gui/
│   │   ├── main.py                # Main GUI entry point
│   │   ├── __init__.py            # Empty (avoid circular imports)
│   │   ├── components/
│   │   │   ├── __init__.py        # Empty (avoid circular imports)
│   │   │   ├── sidebar.py         # Navigation & controls
│   │   │   ├── dashboard.py       # Main dashboard (two-table layout)
│   │   │   ├── synchronization.py # Sync page
│   │   │   ├── client_management.py # Client settings (three columns)
│   │   │   ├── client_details.py  # Individual client view
│   │   │   ├── log_viewer.py      # Log viewer with filters
│   │   │   ├── notifications.py   # Toast component
│   │   │   └── modals.py          # Confirmation dialogs
│   │   └── utils/
│   │       ├── __init__.py        # Empty (avoid circular imports)
│   │       ├── session_state.py   # Streamlit session
│   │       ├── refresh_manager.py # Page refresh logic
│   │       └── env_manager.py     # Environment variables
│   └── models/
│       ├── clients/
│       │   └── client_manager.py  # Client management
│       └── copier/
│           ├── synchronizer.py    # Position synchronization
│           ├── calculator.py      # Position calculations
│           ├── validator.py       # Order validation
│           ├── multi_sync.py      # Multi-client sync
│           └── entities.py        # Data models
├── config/
│   ├── general_settings.json      # Global settings (auto-saved)
│   ├── sync_settings.json         # Sync settings (auto-saved)
│   ├── auto_sync_state.json       # Auto Sync state persistence
│   ├── .bg_cache_pid              # Background cache PID flag
│   └── .cache_updated             # Cache update flag
├── data/
│   ├── clients/
│   │   ├── clients.json           # Client configurations
│   │   ├── slave_1_history.json   # Live history (orders only)
│   │   └── slave_1_history_dry.json # Test history
│   └── cache/
│       └── account_cache.json     # Cached account data
├── logs/
│   └── test.log                   # Application logs (7-day rotation)
├── .env                           # API credentials
├── .streamlit/
│   └── config.toml                # Streamlit configuration
├── app_streamlit_multi.py         # Application entry point
└── requirements.txt               # Dependencies
```

## ⚙️ Configuration

### general_settings.json

```json
{
  "operating_mode": "simulation",
  "trading_limits": {
    "max_order_size": 10000,
    "max_position_value": 50000,
    "min_order_value": 10,
    "max_orders_per_run": 10
  },
  "notifications": {
    "toast_on_error": true,
    "toast_on_success": false,
    "sound_on_error": true,
    "telegram_enabled": false,
    "telegram_bot_token": "",
    "telegram_chat_id": ""
  },
  "error_handling": {
    "retry_count": 3,
    "stop_on_critical": false,
    "max_errors_per_session": 5
  }
}
```

### Operating Modes

| Mode | Description | Orders Sent | History File |
|------|-------------|-------------|--------------|
| `dry_run` | Quick test | ❌ No | `*_history_dry.json` |
| `simulation` | Full test with detailed logs | ❌ No | `*_history_dry.json` |
| `live` | Real trading | ✅ Yes | `*_history.json` |

### .env Configuration

```env
# Logging
LOG_LEVEL=INFO  # DEBUG for verbose logging

# Main Account
MAIN_APP_KEY=your_app_key
MAIN_APP_SECRET=your_app_secret
MAIN_CALLBACK_URL=https://127.0.0.1
MAIN_ACCOUNT_NUMBER=12345678

# Slave Account 1
SLAVE_1_APP_KEY=slave_app_key
SLAVE_1_APP_SECRET=slave_app_secret
SLAVE_1_CALLBACK_URL=https://127.0.0.1
SLAVE_1_ACCOUNT_NUMBER=87654321
```

### .streamlit/config.toml

```toml
[server]
headless = false          # true = don't open browser automatically
runOnSave = false         # Don't restart on file changes
fileWatcherType = "none"  # Disable file watching

[browser]
gatherUsageStats = false
serverAddress = "localhost"

[theme]
base = "dark"
```

## 🖥️ GUI Pages

### Dashboard
- Overview of all accounts (two-table layout)
- Main account positions with current prices
- Client account summaries with sync status
- Quick status indicators (time ago coloring)
- Global Auto Sync indicator in sidebar

### Synchronization
- Status block with last sync time
- Auto Sync controls (Start/Stop)
- Sync interval configuration
- Active hours settings
- Manual sync button

### Client Management (Three Columns)
- **General Settings** - Trading limits, notifications, operating mode (auto-save)
- **Add New Client** - Register new slave accounts
- **Remove Client** - Delete client configurations

### Client Details
- Individual client settings
- Margin configuration
- Scale method selection
- Position history (orders only, optimized)
- Close All Positions button

### Log Viewer
- Real-time log viewing
- Filter by log level (DEBUG, INFO, WARNING, ERROR)
- Search functionality
- Auto-refresh toggle
- Configurable line count

## 📊 Synchronization Logic

### Scale Calculation
```
scale = slave_equity / main_equity
```

### Position Delta
```
target_quantity = main_quantity × scale
delta = target_quantity - current_quantity
```

### Order Validation
1. Check market hours (9:30 AM - 4:00 PM ET)
2. Check market calendar (holidays, weekends)
3. Validate order size limits
4. Check buying power
5. Verify position value limits

### Margin Support
- Configure per client in Client Settings
- Set margin percentage buffer (0-100%)
- Formula: `available = (Total Value × (1 + margin%/100)) - Positions Value`
- Limited by Schwab's reported `buyingPower`

### History Optimization
- **Live mode**: Records only syncs with actual orders
- **Simulation/Dry Run**: First sync writes to history, subsequent iterations skip
- Prevents history bloat during Auto Sync

## 🔄 Auto Sync State Persistence

Auto Sync state is saved to `config/auto_sync_state.json`:

```json
{
  "running": true,
  "started_at": "2026-01-02T04:26:15.123456",
  "interval": "Every 1 minute",
  "pid": 12345
}
```

**Features:**
- Close browser → Auto Sync continues running
- Reopen browser → Stop button appears, can stop the process
- Process crash detection via PID checking
- Works on Windows and Linux

## 🔔 Notifications

### Toast Notifications
- Configurable via GUI
- Toast On Error - Show toast when order fails
- Toast On Success - Show toast when order succeeds

### Sound Alerts
- Windows: System error sound
- Linux/Mac: Terminal bell

### Telegram (Coming Soon)
- Bot Token configuration
- Chat ID configuration
- Real-time order notifications

## 🛡️ Error Handling

### Retry Logic
- Configurable retry count (default: 3)
- Exponential backoff between retries
- Error classification by type:
  - TIMEOUT - Retryable
  - RATE_LIMIT - Retryable
  - UNAUTHORIZED - Not retryable
  - SERVER_ERROR - Retryable
  - BAD_REQUEST - Not retryable

### Error Tracking
- Consecutive error counter
- Maximum errors per session
- Optional stop on critical error

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Schwab API credentials
```

### 3. Run Application
```bash
streamlit run app_streamlit_multi.py
```

Browser opens automatically at `http://localhost:8501`

### 4. First Time Setup
1. Go to **Client Management** → **General Settings**
2. Set Operating Mode to **Simulation**
3. Go to **Client Management** → **Add New Client**
4. Add your slave account credentials
5. Go to **Synchronization**
6. Click **Sync** to test

### 5. Enable Auto Sync
1. Go to **Synchronization**
2. Configure interval (1-60 minutes)
3. Set active hours (e.g., 9:30 AM - 4:00 PM)
4. Click **Start**
5. You can close the browser - sync continues!

### 6. Enable Live Trading
1. Go to **Client Management** → **General Settings**
2. Select **Live Mode**
3. Confirm the warning dialog
4. Click **Sync** during market hours

## ⚠️ Important Notes

1. **Market Hours** - Live orders only work during US market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
2. **Market Holidays** - Automatic detection of US market holidays
3. **API Limits** - Schwab API has rate limits, don't sync too frequently
4. **Test First** - Always test in Simulation mode before going Live
5. **Monitor** - Watch the logs during initial Live trading
6. **Margin** - Be careful with margin settings, they can amplify losses
7. **Browser Close** - Auto Sync survives browser close, use Stop button to stop

## 📝 Logging

### Log Format
```
2026-01-02 04:26:15 | INFO | module:function:line | Message
```

### Log Rotation
- Automatic rotation every 7 days
- Old logs automatically deleted

### Log Levels
- **DEBUG** - Detailed debugging (set LOG_LEVEL=DEBUG in .env)
- **INFO** - Normal operations
- **WARNING** - Potential issues
- **ERROR** - Errors that need attention

## 🔧 Architecture

### Key Components

| Component | Purpose |
|-----------|---------|
| `SyncService` | Global singleton managing Auto Sync |
| `EventScheduler` | Heap-based task scheduler |
| `CacheManager` | Background cache updates |
| `ConfigCache` | Configuration caching (reduces file I/O) |
| `MarketCalendar` | Market hours and holiday detection |

### Threading Model
- **Main Thread** - Streamlit GUI
- **Background Thread** - Cache updates (one per process)
- **Scheduler Thread** - Auto Sync execution

### State Management
- `st.session_state` - Per-browser-tab state
- Global singletons - Shared across all browser tabs
- File-based flags - Survive browser close

## 📜 Changelog

### v1.1.0 (Current)
- Auto Sync state persistence (survives browser close)
- Global SyncService singleton (Stop works from any browser tab)
- Background cache updates with file-based flags
- Log Viewer with filtering and auto-refresh
- Dashboard two-table layout
- Client Management three-column layout
- History optimization (orders only)
- Market calendar integration
- Settings auto-save
- Windows PID checking fix
- Circular import fixes

### v1.0.0
- Initial release
- Multi-client synchronization
- Three operating modes (Dry Run, Simulation, Live)
- Auto Sync with configurable intervals
- Toast notifications
- Sound alerts
- Margin support
- Error handling with retry logic

## 📄 License

MIT License

## 👤 Author

SyncSchwab Position Copier
