
# market_calendar.py
# app.core.market_calendar

from datetime import datetime, date
from typing import Optional, Dict, List
import pytz

from app.core.paths import CONFIG_DIR
from app.core.json_utils import load_json

CALENDAR_FILE = CONFIG_DIR / "market_calendar.json"


def load_market_calendar() -> Dict:
    """Загрузить календарь из файла"""
    return load_json(str(CALENDAR_FILE), default={})


def get_holidays(year: int = None) -> List[Dict]:
    """Получить список праздников"""
    calendar = load_market_calendar()

    if year and calendar.get('year') != year:
        return []

    return calendar.get('holidays', [])


def get_early_close_days(year: int = None) -> List[Dict]:
    """Получить список коротких дней"""
    calendar = load_market_calendar()

    if year and calendar.get('year') != year:
        return []

    return calendar.get('early_close', [])


def is_market_holiday(check_date: date = None) -> bool:
    """Проверить, является ли день праздником"""
    if check_date is None:
        check_date = date.today()

    date_str = check_date.strftime("%Y-%m-%d")
    holidays = get_holidays()

    return any(h['date'] == date_str for h in holidays)


def is_early_close_day(check_date: date = None) -> Optional[str]:
    """
    Проверить, является ли день коротким.
    Возвращает время закрытия или None.
    """
    if check_date is None:
        check_date = date.today()

    date_str = check_date.strftime("%Y-%m-%d")
    early_days = get_early_close_days()

    for day in early_days:
        if day['date'] == date_str:
            return day.get('close_time', '13:00')

    return None


def get_next_holiday() -> Optional[Dict]:
    """Получить следующий праздник"""
    today = date.today()
    holidays = get_holidays()

    for holiday in holidays:
        holiday_date = datetime.strptime(holiday['date'], "%Y-%m-%d").date()
        if holiday_date >= today:
            return holiday

    return None


def get_market_status() -> Dict:
    """
    Получить текущий статус рынка.

    Returns:
        {
            'is_open': bool,
            'status': 'OPEN' | 'CLOSED' | 'PRE_MARKET' | 'AFTER_HOURS' | 'HOLIDAY' | 'WEEKEND',
            'message': str,
            'next_event': str,
            'close_time': str (if early close)
        }
    """
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)
    today = now_et.date()

    result = {
        'is_open': False,
        'status': 'CLOSED',
        'message': '',
        'next_event': '',
        'close_time': None
    }

    # Проверить выходные
    if now_et.weekday() >= 5:  # Сб, Вс
        result['status'] = 'WEEKEND'
        result['message'] = 'Weekend - Market Closed'
        # Рассчитать время до открытия в понедельник
        days_until_monday = 7 - now_et.weekday()
        result['next_event'] = f'Opens Monday 9:30 AM ET'
        return result

    # Проверить праздник
    if is_market_holiday(today):
        holiday = next((h for h in get_holidays() if h['date'] == today.strftime("%Y-%m-%d")), None)
        holiday_name = holiday['name'] if holiday else 'Holiday'
        result['status'] = 'HOLIDAY'
        result['message'] = f'{holiday_name} - Market Closed'
        result['next_event'] = 'Opens next trading day 9:30 AM ET'
        return result

    # Проверить короткий день
    early_close = is_early_close_day(today)
    if early_close:
        result['close_time'] = early_close

    # Определить время закрытия
    close_hour = 13 if early_close else 16
    close_minute = 0

    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)

    # Определить статус
    if now_et < market_open:
        result['status'] = 'PRE_MARKET'
        result['message'] = 'Pre-Market'
        time_to_open = market_open - now_et
        hours, remainder = divmod(time_to_open.seconds, 3600)
        minutes = remainder // 60
        result['next_event'] = f'Opens in {hours}h {minutes}m'

    elif now_et > market_close:
        result['status'] = 'AFTER_HOURS'
        result['message'] = 'After-Hours'
        result['next_event'] = 'Opens tomorrow 9:30 AM ET'

    else:
        result['is_open'] = True
        result['status'] = 'OPEN'
        if early_close:
            result['message'] = f'Market Open (Early Close {early_close})'
        else:
            result['message'] = 'Market Open'
        time_to_close = market_close - now_et
        hours, remainder = divmod(time_to_close.seconds, 3600)
        minutes = remainder // 60
        result['next_event'] = f'Closes in {hours}h {minutes}m'

    return result


def needs_calendar_update() -> bool:
    """Проверить, нужно ли обновить календарь (новый год)"""
    calendar = load_market_calendar()
    current_year = date.today().year

    return calendar.get('year', 0) != current_year