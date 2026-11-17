from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from statistics import mean

VERSION = "V2.2"
INDEX = "000300"
HIT_BAND = 0.01
ISSUE_COUNT = 8
ISSUE_HIT_RATE = 0.60
JUDGED = {"命中", "未命中", "未拉开"}
BASIS_NOTE = (
    "当前申万指数成份，已剔除计入日晚于新闻日的股票。"
    "已调出指数的股票不在篮子里，不是新闻当日的完整历史成份。"
)


def audit(cards: list[dict], *, trading_days: set[date], prices: dict, as_of: date) -> list[dict]:
    """按 V2.2 事件轨道检验一批因子卡片。窗口未结束不判命中。"""
    seen: set[tuple[str, str]] = set()
    evaluated = []
    for card in cards:
        news_id = _news_id(card.get("名称", ""))
        sector = str(card.get("适用赛道") or "")
        key = (news_id, sector)
        if key in seen:
            evaluated.append(_finished(card, as_of, 单次结果="重复", 级别="观察"))
            continue
        seen.add(key)
        evaluated.append(_evaluate(card, trading_days, prices, as_of))
    _mark_cross_industry(evaluated)
    _mark_classes(evaluated)
    return [item["row"] for item in evaluated]


def _evaluate(card: dict, trading_days: set[date], prices: dict, as_of: date) -> dict:
    news = _clock(card.get("新闻时间"))
    until = _clock(card.get("有效期截止"))
    if news is None or until is None:
        return _finished(card, as_of, 单次结果="退回", 级别="退回")
    if card.get("状态") != "pending_verify":
        return _finished(card, as_of, 单次结果="退回", 级别="退回", news=news, until=until)
    sign = _signal_sign(card)
    if sign is None:
        return _finished(card, as_of, 单次结果="退回", 级别="退回", news=news, until=until)
    if card.get("结果类型") == "样例":
        return _finished(card, as_of, 单次结果="不适用", 级别="样例", news=news, until=until)
    held = _window(news, until, trading_days)
    if not card.get("成份股") or card.get("成份说明") == "missing":
        return _finished(
            card, as_of, 单次结果="不可检验", 级别="不可检验", news=news, until=until, held=held, sign=sign
        )
    if held is None:
        return _finished(card, as_of, 单次结果="不可检验", 级别="不可检验", news=news, until=until, sign=sign)
    base, start, end = held
    if as_of <= end:
        return _finished(
            card,
            as_of,
            单次结果="未到期",
            级别="观察",
            news=news,
            until=until,
            held=held,
            sign=sign,
            countable=False,
            in_class=True,
        )
    codes = [str(item.get("code")) for item in card["成份股"]]
    basket, used = _mean_return(codes, prices, base, end)
    index_return, index_used = _mean_return([INDEX], prices, base, end)
    if basket is None or index_used != 1:
        return _finished(
            card, as_of, 单次结果="不可检验", 级别="不可检验", news=news, until=until, held=held, sign=sign
        )
    excess = round(basket - index_return, 6)
    result = _verdict(sign, excess)
    gap, contrast = _level2_contrast(card, prices, base, end)
    return _finished(
        card,
        as_of,
        单次结果=result,
        级别="观察",
        news=news,
        until=until,
        held=held,
        sign=sign,
        excess=excess,
        basket=basket,
        used=used,
        gap=gap,
        contrast=contrast,
        countable=True,
        in_class=True,
    )


def _finished(
    card: dict,
    as_of: date,
    *,
    单次结果: str,
    级别: str,
    news: datetime | None = None,
    until: datetime | None = None,
    held: tuple[date, date, date] | None = None,
    sign: int | None = None,
    excess: float | None = None,
    basket: float | None = None,
    used: int | None = None,
    gap: float | None = None,
    contrast: str = "不适用",
    countable: bool = False,
    in_class: bool = False,
) -> dict:
    admitted = 单次结果 in JUDGED or 单次结果 == "未到期"
    row = {
        "因子类别": "行业方向",
        "名称": card.get("名称"),
        "逻辑": card.get("逻辑"),
        "表达式": card.get("表达式"),
        "适用赛道": card.get("适用赛道"),
        "二级行业": card.get("二级行业"),
        "持仓周期": card.get("持仓周期"),
        "新闻时间": card.get("新闻时间") if news else None,
        "有效期截止": card.get("有效期截止") if until else None,
        "方向": card.get("方向"),
        "带符号分数": card.get("带符号分数"),
        "数据标记": card.get("数据标记"),
        "赋值规则": card.get("赋值规则"),
        "成份说明": card.get("成份说明"),
        "成份口径": card.get("成份口径"),
        "成份口径说明": BASIS_NOTE if card.get("成份口径") == "current_sw_index_entered_by_news_day" else None,
        "成份股数量": len(card.get("成份股") or []),
        "计入成份数": used,
        "上游文件": card.get("上游文件"),
        "检验窗口": None if held is None else f"{held[1].isoformat()}/{held[2].isoformat()}",
        "基准": "沪深300" if admitted or 单次结果 in JUDGED else None,
        "行业超额": excess,
        "单次结果": 单次结果,
        "二级对照差额": gap,
        "二级对照": contrast,
        "跨行业对照": "不适用",
        "中性化": "不适用",
        "样本数": None,
        "命中率": None,
        "平均行业超额": None,
        "级别": 级别,
        "入库时间": as_of.isoformat(),
        "版本号": VERSION,
    }
    keep = 单次结果 in JUDGED or 单次结果 in {"未到期", "不可检验"}
    return {
        "row": row,
        "news_id": _news_id(str(card.get("名称") or "")),
        "event_type": _event_type(str(card.get("名称") or "")),
        "sector": str(card.get("适用赛道") or ""),
        "direction": str(card.get("方向") or ""),
        "score": card.get("带符号分数") if isinstance(card.get("带符号分数"), (int, float)) else None,
        "basket": basket,
        "excess": excess,
        "countable": countable,
        "news_time": news,
        "constituent_note": card.get("成份说明"),
        "in_class": in_class or (keep and 单次结果 == "不可检验"),
        "sign": sign,
    }


def _mark_cross_industry(evaluated: list[dict]) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in evaluated:
        if item["basket"] is not None:
            groups[item["news_id"]].append(item)
    for group in groups.values():
        scores = [item["score"] for item in group]
        label = "不适用"
        if len(group) >= 2 and max(scores) != min(scores):
            label = "符合"
            for left in group:
                for right in group:
                    if left["score"] > right["score"] and left["basket"] <= right["basket"]:
                        label = "不符合"
        for item in group:
            item["row"]["跨行业对照"] = label


def _mark_classes(evaluated: list[dict]) -> None:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for item in evaluated:
        if item["in_class"]:
            groups[(item["event_type"], item["sector"], item["direction"])].append(item)
    for group in groups.values():
        countable = [item for item in group if item["countable"]]
        if len(countable) < ISSUE_COUNT:
            continue
        latest = max(group, key=lambda item: item["news_time"] or datetime.min)
        hit_rate = sum(item["row"]["单次结果"] == "命中" for item in countable) / len(countable)
        average = round(mean(item["excess"] for item in countable), 6)
        sign = 1 if group[0]["direction"] == "positive" else -1
        issue = hit_rate >= ISSUE_HIT_RATE and average * sign > 0 and latest["constituent_note"] != "missing"
        for item in group:
            if item["row"]["单次结果"] in JUDGED or item["row"]["单次结果"] == "未到期":
                item["row"]["样本数"] = len(countable)
                item["row"]["命中率"] = hit_rate
                item["row"]["平均行业超额"] = average
            if item["row"]["单次结果"] in JUDGED:
                item["row"]["级别"] = "可下发" if issue else "观察"


def _level2_contrast(card: dict, prices: dict, base: date, end: date) -> tuple[float | None, str]:
    sector_l2 = card.get("二级行业")
    if not sector_l2 or card.get("成份说明") == "level2_missing":
        return None, "不适用"
    named = [str(item.get("code")) for item in card["成份股"] if item.get("in_level2")]
    others = [str(item.get("code")) for item in card["成份股"] if not item.get("in_level2")]
    if not named or not others:
        return None, "不适用"
    named_return, named_used = _mean_return(named, prices, base, end)
    other_return, other_used = _mean_return(others, prices, base, end)
    if named_used == 0 or other_used == 0:
        return None, "不适用"
    gap = round(named_return - other_return, 6)
    return gap, "二级更强" if named_return > other_return else "二级不更强"


def _mean_return(codes: list[str], prices: dict, base: date, end: date) -> tuple[float | None, int]:
    returns = []
    for code in codes:
        series = prices.get(code) or {}
        start_px = series.get(base)
        end_px = series.get(end)
        if start_px is None or end_px is None or start_px <= 0:
            continue
        returns.append(round(end_px / start_px - 1, 6))
    if not returns:
        return None, 0
    return mean(returns), len(returns)


def _verdict(sign: int, excess: float) -> str:
    if abs(excess) < HIT_BAND:
        return "未拉开"
    if excess * sign > 0:
        return "命中"
    return "未命中"


def _window(news: datetime, until: datetime, trading_days: set[date]) -> tuple[date, date, date] | None:
    news_day = news.date()
    until_day = until.date()
    base_days = [day for day in trading_days if day <= news_day]
    start_days = [day for day in trading_days if day > news_day]
    end_days = [day for day in trading_days if day <= until_day]
    if not base_days or not start_days or not end_days:
        return None
    base, start, end = max(base_days), min(start_days), max(end_days)
    if start > end:
        return None
    return base, start, end


def _signal_sign(card: dict) -> int | None:
    direction = card.get("方向")
    score = card.get("带符号分数")
    if direction == "positive":
        sign = 1
    elif direction == "negative":
        sign = -1
    else:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    if score == 0 or (score > 0) != (sign > 0):
        return None
    return sign


def _clock(value) -> datetime | None:
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _news_id(name: str) -> str:
    return name.rsplit("_", 1)[-1]


def _event_type(name: str) -> str:
    return name.split("_", 1)[0]
