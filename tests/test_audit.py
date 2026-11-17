from datetime import date, datetime

from factor_check.audit import audit

DAY = {
    16: date(2026, 11, 16),
    17: date(2026, 11, 17),
    18: date(2026, 11, 18),
    19: date(2026, 11, 19),
    20: date(2026, 11, 20),
    21: date(2026, 11, 21),
}
TRADING = {DAY[16], DAY[17], DAY[18], DAY[19], DAY[20]}


def card(**overrides):
    base = {
        "名称": "tech_电子_positive_n1",
        "逻辑": "示例逻辑",
        "表达式": "signed_score = 1 * 0.72",
        "适用赛道": "电子",
        "二级行业": None,
        "持仓周期": "1至5日",
        "新闻时间": "2026-11-16T09:00:00",
        "有效期截止": "2026-11-18T09:00:00",
        "方向": "positive",
        "带符号分数": 0.72,
        "数据标记": "qualitative_only",
        "赋值规则": "有效期内等于带符号分数",
        "成份说明": "ok",
        "成份口径": "current_sw_index_entered_by_news_day",
        "成份股": [{"code": "600000", "name": "甲", "in_level2": False}],
        "结果类型": "实时",
        "状态": "pending_verify",
    }
    base.update(overrides)
    return base


def prices_for(stock_end, index_end=100.0, code="600000"):
    return {
        "000300": {DAY[16]: 100.0, DAY[18]: index_end},
        code: {DAY[16]: 100.0, DAY[18]: stock_end},
    }


def one(cards, prices, as_of=DAY[19]):
    rows = audit(cards, trading_days=TRADING, prices=prices, as_of=as_of)
    assert len(rows) == len(cards)
    return rows[0]


def test_open_window_is_not_judged():
    row = one([card()], prices_for(110.0), as_of=DAY[18])
    assert row["单次结果"] == "未到期"
    assert row["行业超额"] is None
    assert row["级别"] == "观察"
    assert row["样本数"] is None


def test_excess_subtracts_the_index():
    row = one([card()], prices_for(110.0, index_end=105.0))
    assert row["行业超额"] == 0.05
    assert row["单次结果"] == "命中"


def test_closed_window_excludes_the_news_day_move():
    book = prices_for(110.0)
    book["600000"][date(2026, 11, 13)] = 50.0
    row = one([card()], book)
    assert row["检验窗口"] == "2026-11-17/2026-11-18"
    assert row["行业超额"] == 0.1
    assert row["单次结果"] == "命中"
    assert row["基准"] == "沪深300"
    assert row["中性化"] == "不适用"
    assert "IC" not in row
    assert "Rank IC" not in row


def test_weekend_end_stops_on_the_previous_trading_day():
    row = one(
        [card(有效期截止="2026-11-21T20:26:36")],
        {
            "000300": {DAY[16]: 100.0, DAY[20]: 100.0},
            "600000": {DAY[16]: 100.0, DAY[20]: 110.0},
        },
        as_of=date(2026, 11, 23),
    )
    assert row["检验窗口"] == "2026-11-17/2026-11-20"
    assert row["单次结果"] == "命中"


def test_one_percent_band_and_negative_signal():
    flat = one([card()], prices_for(100.5))
    assert flat["单次结果"] == "未拉开"
    edge = one([card()], prices_for(101.0))
    assert edge["单次结果"] == "命中"
    miss = one(
        [card(名称="tech_电子_negative_n1", 方向="negative", 带符号分数=-0.45)],
        prices_for(103.0),
    )
    assert miss["单次结果"] == "未命中"
    hit = one(
        [card(名称="tech_电子_negative_n2", 方向="negative", 带符号分数=-0.45)],
        prices_for(97.0),
    )
    assert hit["单次结果"] == "命中"


def test_sample_and_missing_constituents_are_not_return_tested():
    sample = one([card(结果类型="样例", 成份说明="样例")], {})
    assert sample["级别"] == "样例"
    assert sample["单次结果"] == "不适用"
    assert sample["行业超额"] is None
    missing = one([card(成份说明="missing", 成份股=[])], {})
    assert missing["级别"] == "不可检验"
    assert missing["单次结果"] == "不可检验"
    broken = one([card(新闻时间="2026-11-16")], {})
    assert broken["级别"] == "退回"
    assert broken["单次结果"] == "退回"


def test_level2_missing_still_tests_the_level_one_basket():
    row = one(
        [card(二级行业="半导体", 成份说明="level2_missing")],
        prices_for(110.0),
    )
    assert row["单次结果"] == "命中"
    assert row["二级对照"] == "不适用"
    assert row["二级对照差额"] is None


def test_fewer_than_eight_keeps_an_empty_class_summary():
    row = one([card()], prices_for(110.0))
    assert row["级别"] == "观察"
    assert row["样本数"] is None
    assert row["命中率"] is None
    assert row["平均行业超额"] is None


def test_eight_hits_with_matching_average_can_be_issued():
    cards = [
        card(名称=f"tech_电子_positive_n{i}", 成份股=[{"code": f"60000{i}", "name": "甲", "in_level2": False}])
        for i in range(8)
    ]
    book = {"000300": {DAY[16]: 100.0, DAY[18]: 100.0}}
    for i in range(8):
        book[f"60000{i}"] = {DAY[16]: 100.0, DAY[18]: 110.0}
    rows = audit(cards, trading_days=TRADING, prices=book, as_of=DAY[19])
    assert {row["级别"] for row in rows} == {"可下发"}
    assert rows[0]["样本数"] == 8
    assert rows[0]["命中率"] == 1.0
    assert rows[0]["平均行业超额"] == 0.1


def test_low_hit_rate_or_wrong_sign_average_stays_under_observation():
    cards = []
    book = {"000300": {DAY[16]: 100.0, DAY[18]: 100.0}}
    for i, end in enumerate([110, 110, 110, 110, 90, 90, 90, 90]):
        code = f"60010{i}"
        cards.append(card(名称=f"tech_电子_positive_h{i}", 成份股=[{"code": code, "name": "甲", "in_level2": False}]))
        book[code] = {DAY[16]: 100.0, DAY[18]: float(end)}
    rows = audit(cards, trading_days=TRADING, prices=book, as_of=DAY[19])
    assert rows[0]["样本数"] == 8
    assert rows[0]["命中率"] == 0.5
    assert rows[0]["级别"] == "观察"

    cards = []
    book = {"000300": {DAY[16]: 100.0, DAY[18]: 100.0}}
    ends = [101, 101, 101, 101, 101, 90, 90, 90]
    for i, end in enumerate(ends):
        code = f"60020{i}"
        cards.append(
            card(名称=f"tech_电子_positive_w{i}", 成份股=[{"code": code, "name": "甲", "in_level2": False}])
        )
        book[code] = {DAY[16]: 100.0, DAY[18]: float(end)}
    rows = audit(cards, trading_days=TRADING, prices=book, as_of=DAY[19])
    assert rows[0]["命中率"] == 0.625
    assert rows[0]["平均行业超额"] < 0
    assert rows[0]["级别"] == "观察"


def test_latest_missing_constituents_block_issue():
    cards = [
        card(名称=f"tech_电子_positive_n{i}", 成份股=[{"code": "600000", "name": "甲", "in_level2": False}])
        for i in range(8)
    ]
    cards.append(
        card(
            名称="tech_电子_positive_late",
            新闻时间="2026-11-16T18:00:00",
            成份说明="missing",
            成份股=[],
        )
    )
    rows = audit(cards, trading_days=TRADING, prices=prices_for(110.0), as_of=DAY[19])
    issued = [row for row in rows if row["名称"] != "tech_电子_positive_late"]
    assert {row["级别"] for row in issued} == {"观察"}
    assert rows[-1]["级别"] == "不可检验"


def test_cross_industry_rank_only_when_scores_differ():
    shared = "c0ffee"
    high = card(名称=f"tech_电子_positive_{shared}", 带符号分数=0.72, 成份股=[{"code": "600001", "name": "甲", "in_level2": False}])
    low = card(
        名称=f"tech_银行_positive_{shared}",
        适用赛道="银行",
        带符号分数=0.40,
        成份股=[{"code": "600002", "name": "乙", "in_level2": False}],
    )
    book = {
        "000300": {DAY[16]: 100.0, DAY[18]: 100.0},
        "600001": {DAY[16]: 100.0, DAY[18]: 108.0},
        "600002": {DAY[16]: 100.0, DAY[18]: 101.0},
    }
    rows = audit([high, low], trading_days=TRADING, prices=book, as_of=DAY[19])
    assert {row["跨行业对照"] for row in rows} == {"符合"}

    book["600002"][DAY[18]] = 112.0
    rows = audit([high, low], trading_days=TRADING, prices=book, as_of=DAY[19])
    assert {row["跨行业对照"] for row in rows} == {"不符合"}

    low["带符号分数"] = 0.72
    rows = audit([high, low], trading_days=TRADING, prices=book, as_of=DAY[19])
    assert {row["跨行业对照"] for row in rows} == {"不适用"}


def test_level2_subset_should_be_stronger_and_a_halt_is_dropped():
    members = [
        {"code": "600001", "name": "二级甲", "in_level2": True},
        {"code": "600002", "name": "二级乙", "in_level2": True},
        {"code": "600003", "name": "其他", "in_level2": False},
        {"code": "600004", "name": "停牌", "in_level2": False},
    ]
    book = {
        "000300": {DAY[16]: 100.0, DAY[18]: 100.0},
        "600001": {DAY[16]: 100.0, DAY[18]: 120.0},
        "600002": {DAY[16]: 100.0, DAY[18]: 110.0},
        "600003": {DAY[16]: 100.0, DAY[18]: 100.0},
        "600004": {DAY[16]: 100.0},
    }
    row = one([card(二级行业="半导体", 成份股=members)], book)
    assert row["单次结果"] == "命中"
    assert row["二级对照差额"] == 0.15
    assert row["二级对照"] == "二级更强"
    assert row["计入成份数"] == 3


def test_duplicate_news_and_sector_keeps_one_card():
    first = card(名称="tech_电子_positive_same")
    second = card(名称="tech_电子_positive_same", 逻辑="另一张")
    rows = audit([first, second], trading_days=TRADING, prices=prices_for(110.0), as_of=DAY[19])
    assert rows[0]["单次结果"] == "命中"
    assert rows[1]["单次结果"] == "重复"
    assert rows[1]["级别"] == "观察"


def test_unfinished_events_do_not_count_toward_eight():
    cards = [
        card(名称=f"tech_电子_positive_n{i}", 成份股=[{"code": "600000", "name": "甲", "in_level2": False}])
        for i in range(7)
    ]
    cards.append(
        card(名称="tech_电子_positive_open", 有效期截止="2026-11-20T09:00:00")
    )
    rows = audit(cards, trading_days=TRADING, prices=prices_for(110.0), as_of=DAY[19])
    assert rows[-1]["单次结果"] == "未到期"
    assert rows[0]["样本数"] is None
    assert rows[0]["级别"] == "观察"
