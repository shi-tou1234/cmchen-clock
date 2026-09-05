"""时钟显示文本格式化（纯函数，不依赖 GUI）。"""

AM = "AM"
PM = "PM"


def format_time(hour, minute, second=0, show_seconds=True, hour24=True):
    """格式化时间文本。

    24 小时制: "HH:MM" / "HH:MM:SS"（补零）。
    12 小时制: "H:MM AM/PM" / "H:MM:SS AM/PM"（小时不补零，零点与正午记作 12）。
    参数越界抛 ValueError。
    """
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError(f"invalid time: {hour:02d}:{minute:02d}:{second:02d}")
    if hour24:
        base = f"{hour:02d}:{minute:02d}"
        if show_seconds:
            base += f":{second:02d}"
        return base
    suffix = AM if hour < 12 else PM
    hour12 = hour % 12 or 12
    base = f"{hour12}:{minute:02d}"
    if show_seconds:
        base += f":{second:02d}"
    return f"{base} {suffix}"


def format_date(year, month, day):
    """格式化日期文本 "yyyy-MM-dd"（补零）。参数越界抛 ValueError。"""
    if not (1 <= month <= 12 and 1 <= day <= 31 and year > 0):
        raise ValueError(f"invalid date: {year}-{month:02d}-{day:02d}")
    return f"{year:04d}-{month:02d}-{day:02d}"
