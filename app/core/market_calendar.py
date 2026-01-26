
# market_calendar.py
# app.core.market_calendar

from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
import pytz

from app.core.paths import CONFIG_DIR
from app.core.json_utils import load_json, save_json
from app.core.logger import logger

CALENDAR_FILE = CONFIG_DIR / "market_calendar.json"


# ═══════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ КАЛЕНДАРЯ
# ═══════════════════════════════════════════════════════════════

def _get_nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """
    Получить n-й день недели в месяце.
    
    Args:
        year: Год
        month: Месяц (1-12)
        weekday: День недели (0=пн, 1=вт, ..., 6=вс)
        n: Какой по счёту (1=первый, 2=второй, ..., -1=последний)
    
    Returns:
        date объект
    """
    if n > 0:
        # Первый день месяца
        first_day = date(year, month, 1)
        # Сколько дней до нужного дня недели
        days_ahead = weekday - first_day.weekday()
        if days_ahead < 0:
            days_ahead += 7
        # Первый такой день недели
        first_weekday = first_day + timedelta(days=days_ahead)
        # n-й такой день
        return first_weekday + timedelta(weeks=n-1)
    else:
        # Последний день месяца
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        # Сколько дней назад до нужного дня недели
        days_back = last_day.weekday() - weekday
        if days_back < 0:
            days_back += 7
        return last_day - timedelta(days=days_back)


def _calculate_easter(year: int) -> date:
    """
    Вычислить дату Пасхи (алгоритм Anonymous Gregorian).
    Good Friday = Пасха - 2 дня.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _adjust_for_weekend(holiday_date: date) -> date:
    """
    Корректировка праздника если выпадает на выходной.
    Суббота → пятница, Воскресенье → понедельник.
    """
    if holiday_date.weekday() == 5:  # Суббота
        return holiday_date - timedelta(days=1)
    elif holiday_date.weekday() == 6:  # Воскресенье
        return holiday_date + timedelta(days=1)
    return holiday_date


def generate_holidays(year: int) -> List[Dict]:
    """
    Генерация списка праздников NYSE для года.
    
    Args:
        year: Год для генерации
        
    Returns:
        Список праздников [{date, name}, ...]
    """
    holidays = []
    
    # 1. New Year's Day - 1 января
    new_year = _adjust_for_weekend(date(year, 1, 1))
    holidays.append({
        "date": new_year.strftime("%Y-%m-%d"),
        "name": "New Year's Day"
    })
    
    # 2. Martin Luther King Jr. Day - 3-й понедельник января
    mlk = _get_nth_weekday(year, 1, 0, 3)
    holidays.append({
        "date": mlk.strftime("%Y-%m-%d"),
        "name": "Martin Luther King Jr. Day"
    })
    
    # 3. Presidents Day - 3-й понедельник февраля
    presidents = _get_nth_weekday(year, 2, 0, 3)
    holidays.append({
        "date": presidents.strftime("%Y-%m-%d"),
        "name": "Presidents Day"
    })
    
    # 4. Good Friday - пятница перед Пасхой
    easter = _calculate_easter(year)
    good_friday = easter - timedelta(days=2)
    holidays.append({
        "date": good_friday.strftime("%Y-%m-%d"),
        "name": "Good Friday"
    })
    
    # 5. Memorial Day - последний понедельник мая
    memorial = _get_nth_weekday(year, 5, 0, -1)
    holidays.append({
        "date": memorial.strftime("%Y-%m-%d"),
        "name": "Memorial Day"
    })
    
    # 6. Juneteenth - 19 июня
    juneteenth = _adjust_for_weekend(date(year, 6, 19))
    holidays.append({
        "date": juneteenth.strftime("%Y-%m-%d"),
        "name": "Juneteenth"
    })
    
    # 7. Independence Day - 4 июля
    independence = _adjust_for_weekend(date(year, 7, 4))
    holidays.append({
        "date": independence.strftime("%Y-%m-%d"),
        "name": "Independence Day"
    })
    
    # 8. Labor Day - 1-й понедельник сентября
    labor = _get_nth_weekday(year, 9, 0, 1)
    holidays.append({
        "date": labor.strftime("%Y-%m-%d"),
        "name": "Labor Day"
    })
    
    # 9. Thanksgiving - 4-й четверг ноября
    thanksgiving = _get_nth_weekday(year, 11, 3, 4)
    holidays.append({
        "date": thanksgiving.strftime("%Y-%m-%d"),
        "name": "Thanksgiving Day"
    })
    
    # 10. Christmas - 25 декабря
    christmas = _adjust_for_weekend(date(year, 12, 25))
    holidays.append({
        "date": christmas.strftime("%Y-%m-%d"),
        "name": "Christmas Day"
    })
    
    return holidays


def generate_early_close_days(year: int) -> List[Dict]:
    """
    Генерация списка коротких дней NYSE для года.
    
    Args:
        year: Год для генерации
        
    Returns:
        Список коротких дней [{date, name, close_time}, ...]
    """
    early_close = []
    
    # 1. День перед Independence Day (3 июля, если будний)
    independence = date(year, 7, 4)
    day_before_july4 = independence - timedelta(days=1)
    # Если 3 июля - будний день и 4 июля не суббота
    if day_before_july4.weekday() < 5 and independence.weekday() != 5:
        early_close.append({
            "date": day_before_july4.strftime("%Y-%m-%d"),
            "name": "Day before Independence Day",
            "close_time": "13:00"
        })
    
    # 2. День после Thanksgiving (пятница)
    thanksgiving = _get_nth_weekday(year, 11, 3, 4)
    day_after_thanksgiving = thanksgiving + timedelta(days=1)
    early_close.append({
        "date": day_after_thanksgiving.strftime("%Y-%m-%d"),
        "name": "Day after Thanksgiving",
        "close_time": "13:00"
    })
    
    # 3. Christmas Eve (24 декабря, если будний)
    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < 5:  # Будний день
        early_close.append({
            "date": christmas_eve.strftime("%Y-%m-%d"),
            "name": "Christmas Eve",
            "close_time": "13:00"
        })
    
    return early_close


def generate_market_calendar(year: int, include_next_year: bool = True) -> Dict:
    """
    Генерация полного календаря NYSE.
    
    Args:
        year: Основной год
        include_next_year: Включить праздники следующего года (для декабря)
        
    Returns:
        Полный календарь {year, last_updated, holidays, early_close, regular_hours}
    """
    holidays = generate_holidays(year)
    early_close = generate_early_close_days(year)
    
    # Добавить следующий год если нужно
    if include_next_year:
        holidays.extend(generate_holidays(year + 1))
        early_close.extend(generate_early_close_days(year + 1))
    
    # Сортировать по дате
    holidays.sort(key=lambda x: x['date'])
    early_close.sort(key=lambda x: x['date'])
    
    calendar = {
        "year": year,
        "last_updated": date.today().strftime("%Y-%m-%d"),
        "holidays": holidays,
        "early_close": early_close,
        "regular_hours": {
            "open": "09:30",
            "close": "16:00",
            "timezone": "US/Eastern"
        }
    }
    
    return calendar


def update_market_calendar() -> bool:
    """
    Обновить файл календаря если нужно.
    
    Returns:
        True если календарь был обновлён
    """
    if not needs_calendar_update():
        return False
    
    current_year = date.today().year
    calendar = generate_market_calendar(current_year, include_next_year=True)
    
    save_json(str(CALENDAR_FILE), calendar)
    logger.info(f"📅 Market calendar updated for {current_year}-{current_year + 1}")
    
    return True


# ═══════════════════════════════════════════════════════════════
# ЗАГРУЗКА И ЧТЕНИЕ КАЛЕНДАРЯ
# ═══════════════════════════════════════════════════════════════

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
        result['next_event'] = 'Opens Monday 9:30 AM ET'
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
    """
    Проверить, нужно ли обновить календарь.
    
    Обновляем если:
    - Год в календаре не текущий
    - Или мы в декабре и нет данных на следующий год
    """
    from datetime import date
    
    calendar = load_market_calendar()
    current_year = date.today().year
    current_month = date.today().month
    
    calendar_year = calendar.get('year', 0)
    
    # Если год не текущий — нужно обновить
    if calendar_year != current_year:
        return True
    
    # Если декабрь — проверить есть ли данные на следующий год
    if current_month == 12:
        holidays = calendar.get('holidays', [])
        next_year = current_year + 1
        has_next_year = any(
            h.get('date', '').startswith(str(next_year)) 
            for h in holidays
        )
        if not has_next_year:
            return True
    
    return False


def ensure_calendar_loaded() -> None:
    """
    Проверить и обновить календарь при необходимости.
    Вызывать при запуске приложения.
    """
    # Если файл не существует или нужно обновить
    if not CALENDAR_FILE.exists() or needs_calendar_update():
        update_market_calendar()