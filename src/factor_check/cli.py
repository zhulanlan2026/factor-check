from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from factor_check.audit import INDEX, VERSION, _clock, _signal_sign, _window, audit
from factor_check.prices import load_closes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检验上游交来的行业方向因子")
    parser.add_argument("--factors", required=True, help="上游因子 JSON 目录")
    parser.add_argument("--out", required=True, help="检验档案输出目录")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="检验日，YYYY-MM-DD")
    args = parser.parse_args(argv)
    as_of = date.fromisoformat(args.as_of)
    cards = _load_cards(Path(args.factors))
    trading_days = _trading_days()
    prices = _prices_for_closed_windows(cards, trading_days, as_of)
    rows = audit(cards, trading_days=trading_days, prices=prices, as_of=as_of)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "audits.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "版本": VERSION,
        "检验日": as_of.isoformat(),
        "因子数": len(rows),
        "单次结果": dict(Counter(row["单次结果"] for row in rows)),
        "级别": dict(Counter(row["级别"] for row in rows)),
        "可下发": sum(row["级别"] == "可下发" for row in rows),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _load_cards(folder: Path) -> list[dict]:
    cards = []
    for path in sorted(folder.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        card["上游文件"] = path.name
        cards.append(card)
    return cards


def _prices_for_closed_windows(cards: list[dict], trading_days: set[date], as_of: date) -> dict:
    codes: set[str] = set()
    start: date | None = None
    end: date | None = None
    for card in cards:
        news = _clock(card.get("新闻时间"))
        until = _clock(card.get("有效期截止"))
        if news is None or until is None or card.get("状态") != "pending_verify":
            continue
        if card.get("结果类型") == "样例" or _signal_sign(card) is None:
            continue
        if not card.get("成份股") or card.get("成份说明") == "missing":
            continue
        held = _window(news, until, trading_days)
        if held is None or as_of <= held[2]:
            continue
        base, _, window_end = held
        codes.update(str(item.get("code")) for item in card["成份股"])
        start = base if start is None else min(start, base)
        end = window_end if end is None else max(end, window_end)
    if not codes or start is None or end is None:
        return {}
    codes.add(INDEX)
    return load_closes(codes, start, end)


def _trading_days() -> set[date]:
    import akshare as ak

    frame = ak.calendar_trade_date_hist_sina()
    column = "trade_date" if "trade_date" in frame.columns else frame.columns[0]
    days = set()
    for value in frame[column]:
        if isinstance(value, datetime):
            days.add(value.date())
        elif isinstance(value, date):
            days.add(value)
        else:
            days.add(date.fromisoformat(str(value)[:10]))
    return days
