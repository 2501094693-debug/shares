"""散户过滤与立场/行动词典。LLM 只处理规则判不清的句子。"""

from __future__ import annotations

import re
from typing import Any

STANCES = ("bull", "bear", "mixed", "unclear")
ACTIONS = ("buy", "sell", "wait", "none")

NON_RETAIL_KINDS = {"news", "reports", "notices", "qa", "meeting", "margin"}
KOL_FOLLOWERS = 10_000

_BULL = (
    "看多",
    "做多",
    "看好",
    "看涨",
    "牛市",
    "反包",
    "突破",
    "起飞",
    "拉升",
    "翻倍",
    "主升",
    "钻石手",
    "拿住",
    "持股",
    "还有空间",
    "低估",
    "抄到底",
    "底部",
    "阳线",
    "红盘",
    "暴涨",
)
_BEAR = (
    "看空",
    "做空",
    "看跌",
    "看衰",
    "出货",
    "砸盘",
    "崩了",
    "暴跌",
    "阴跌",
    "垃圾",
    "造假",
    "雷",
    "套牢",
    "深套",
    "完蛋",
    "退市",
    "跑路",
    "利空",
    "高位",
    "泡沫",
    "不要碰",
)
_BUY = (
    "买入",
    "买进",
    "加仓",
    "建仓",
    "开仓",
    "抄底",
    "满仓",
    "追涨",
    "上车",
    "补仓",
    "进场",
    "拿货",
    "吸筹",
    "继续买",
)
_SELL = (
    "卖出",
    "卖掉",
    "减仓",
    "清仓",
    "割肉",
    "止盈",
    "止损",
    "跑了",
    "出掉",
    "离场",
    "兑现",
    "落袋",
    "不想玩",
)
_WAIT = (
    "观望",
    "等待",
    "再看看",
    "等回调",
    "等一等",
    "躺平",
    "持币",
    "空仓等",
    "不急",
    "看看再说",
    "先观察",
    "等消息",
    "等等",
)

_INSTITUTION_RE = re.compile(
    r"(研报|证券时报|券商|资管|私募|公募|基金经理|官方|董秘|记者|资讯平台|"
    r"东方财富网|同花顺财经|财经媒体|广告|加微信|推荐个股)",
)
_KOL_TAGS = {"v", "机构", "认证", "kol", "vip", "达人"}


def _hit_count(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w in text)


def classify_text(text: str) -> dict[str, Any]:
    blob = (text or "").strip()
    if len(blob) < 2:
        return {"stance": "unclear", "action": "none", "confidence": 0.2, "via": "rules"}

    bull = _hit_count(blob, _BULL)
    bear = _hit_count(blob, _BEAR)
    buy = _hit_count(blob, _BUY)
    sell = _hit_count(blob, _SELL)
    wait = _hit_count(blob, _WAIT)

    if "加仓" in blob or "买入" in blob or "抄底" in blob:
        bull += 1
        buy += 1
    if "割" in blob or "清仓" in blob or "减仓" in blob:
        bear += 1
        sell += 1

    if bull and bear:
        stance = "mixed"
    elif bull > bear:
        stance = "bull"
    elif bear > bull:
        stance = "bear"
    else:
        stance = "unclear"

    action_scores = {"buy": buy, "sell": sell, "wait": wait}
    top = max(action_scores, key=action_scores.get)
    tied = [k for k, v in action_scores.items() if v == action_scores[top] and v > 0]
    if action_scores[top] <= 0:
        action = "none"
    elif len(tied) > 1:
        action = "none"
        if stance == "unclear":
            stance = "mixed"
    else:
        action = top

    hits = bull + bear + buy + sell + wait
    if hits == 0:
        confidence = 0.25
    elif stance == "mixed" or (action == "none" and stance == "unclear"):
        confidence = 0.45
    else:
        confidence = min(0.9, 0.5 + 0.1 * hits)

    return {
        "stance": stance,
        "action": action,
        "confidence": round(confidence, 2),
        "via": "rules",
    }


def needs_llm(label: dict[str, Any]) -> bool:
    if (label.get("stance") == "unclear" and label.get("action") in {"none", "wait"}) or label.get(
        "stance"
    ) == "mixed":
        return True
    return float(label.get("confidence") or 0) < 0.5


def is_retail_comment(row: dict[str, Any]) -> tuple[bool, str]:
    kind = str(row.get("kind") or "").lower()
    if kind in NON_RETAIL_KINDS:
        return False, f"kind:{kind}"
    channel = str(row.get("channel") or "")
    if channel in {"guba_news", "xq_news"}:
        return False, "channel"
    author = str(row.get("author") or "")
    media = str(row.get("media_name") or "")
    text = str(row.get("text") or "")
    blob = f"{author} {media} {text[:80]}"
    if _INSTITUTION_RE.search(blob):
        return False, "institution"
    tag = str(row.get("identity_tag") or row.get("user_tag") or "").lower()
    if tag in _KOL_TAGS:
        return False, f"tag:{tag}"
    followers = int(row.get("followers_count") or 0)
    if followers >= KOL_FOLLOWERS:
        return False, "kol_followers"
    if row.get("verified"):
        return False, "verified"
    return True, ""


def user_key(row: dict[str, Any]) -> str:
    source = str(row.get("source") or "")
    uid = str(row.get("author_id") or "").strip()
    author = str(row.get("author") or "").strip()
    return f"{source}:{uid or author or row.get('id')}"
