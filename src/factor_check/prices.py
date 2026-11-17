from __future__ import annotations

from datetime import date, datetime

INDEX = "000300"


def load_closes(codes: set[str], start: date, end: date) -> dict[str, dict[date, float]]:
    """前复权收盘价。停牌日没有记录，调用方不会把缺失填成 0。"""
    import akshare as ak

    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")
    book: dict[str, dict[date, float]] = {}
    for code in sorted(codes):
        if code == INDEX:
            frame = ak.index_zh_hist_em(symbol=INDEX, period="daily", start_date=start_s, end_date=end_s)
        else:
            frame = ak.stock_zh_a_hist_em(
                symbol=code, period="daily", start_date=start_s, end_date=end_s, adjust="qfq"
            )
        book[code] = {
            _as_date(row["日期"]): float(row["收盘"])
            for _, row in frame.iterrows()
            if row["收盘"] == row["收盘"]
        }
    return book


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
