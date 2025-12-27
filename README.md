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
- **Manual Sync** - On-demand synchronization
- **Margin support** - Configure margin usage per client
- **Toast notifications** - Real-time notifications for errors/success
- **Sound alerts** - Audio notification on errors
- **Telegram integration** - (Coming soon) Send notifications to Telegram

## 📁 Project Structure

```
SyncSchwab/
├── app/
│   ├── core/
│   │   ├── config.py              # API configuration
│   │   ├── logger.py              # Logging setup
│   │   ├── json_utils.py          # JSON utilities
│   │   ├── sync_service.py        # Synchronization service
│   │   ├── error_handler.py       # Error handling & retry logic
│   │   └── notification_service.py # Toast notifications
│   ├── gui/
│   │   ├── main.py                # Main GUI entry point
│   │   ├── components/
│   │   │   ├── sidebar.py         # Navigation & controls
│   │   │   ├── dashboard.py       # Main dashboard
│   │   │   ├── synchronization.py # Sync page
│   │   │   ├── client_management.py # Client settings
│   │   │   └── notifications.py   # Toast component
│   │   └── utils/
│   │       ├── session_state.py   # Streamlit session
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
│   ├── general_settings.json      # Global settings
│   └── sync_settings.json         # Sync settings
├── data/
│   ├── clients/
│   │   ├── clients.json           # Client configurations
│   │   ├── slave_1_history.json   # Live history
│   │   └── slave_1_history_dry.json # Test history
│   └── cache/
│       └── account_cache.json     # Cached account data
├── logs/
│   └── test.log                   # Application logs
├── .env                           # API credentials
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

## 🖥️ GUI Pages

### Dashboard
- Overview of all accounts
- Main account positions
- Client account summaries
- Quick status indicators

### Synchronization
- Status block with last sync time
- Auto Sync controls (Start/Stop)
- Sync interval configuration
- Active hours settings
- Manual sync button

### Client Management
- **General Settings** - Trading limits, notifications, operating mode
- **Add New Client** - Register new slave accounts
- **Remove Client** - Delete client configurations

### Client Details
- Individual client settings
- Margin configuration
- Scale method selection
- Position history

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
2. Validate order size limits
3. Check buying power
4. Verify position value limits

### Margin Support
- Configure per client in Client Settings
- Set margin percentage buffer (0-100%)
- Formula: `available = (Total Value × (1 + margin%/100)) - Positions Value`
- Limited by Schwab's reported `buyingPower`

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

### 4. First Time Setup
1. Open browser at `http://localhost:8501`
2. Go to **Client Management** → **General Settings**
3. Set Operating Mode to **Simulation Live**
4. Go to **Client Management** → **Add New Client**
5. Add your slave account credentials
6. Go to **Synchronization**
7. Click **Sync** to test

### 5. Enable Live Trading
1. Go to **Client Management** → **General Settings**
2. Select **Live Mode**
3. Confirm the warning dialog
4. Click **Sync** during market hours

## ⚠️ Important Notes

1. **Market Hours** - Live orders only work during US market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
2. **API Limits** - Schwab API has rate limits, don't sync too frequently
3. **Test First** - Always test in Simulation mode before going Live
4. **Monitor** - Watch the logs during initial Live trading
5. **Margin** - Be careful with margin settings, they can amplify losses

## 📝 Changelog

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
