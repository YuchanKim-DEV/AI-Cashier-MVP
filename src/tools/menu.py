"""
메뉴 데이터 및 recommend_menu function call 핸들러.

MVP: 하드코딩 메뉴. 추후 DB로 교체 가능하도록 MENU_BY_NAME 딕셔너리로 단순화.
find_item 은 별칭(감튀→감자튀김) + 퍼지 매칭(STT 오타 지즈버거→치즈버거)까지 지원.
"""

import difflib
import re
from typing import Optional

MENU_DATA: dict = {
    "버거": [
        {"id": "b1", "name": "치즈버거",   "price": 6500},
        {"id": "b2", "name": "더블버거",   "price": 8500},
        {"id": "b3", "name": "베이컨버거", "price": 7500},
        {"id": "b4", "name": "새우버거",   "price": 7000},
        {"id": "b5", "name": "불고기버거", "price": 7000},
    ],
    "사이드": [
        {"id": "s1", "name": "감자튀김",   "price": 2500},
        {"id": "s2", "name": "양파링",     "price": 3000},
        {"id": "s3", "name": "치킨텐더",   "price": 4500},
        {"id": "s4", "name": "코울슬로",   "price": 2000},
    ],
    "음료": [
        {"id": "d1", "name": "콜라",       "price": 2000},
        {"id": "d2", "name": "사이다",     "price": 2000},
        {"id": "d3", "name": "아이스티",   "price": 2500},
        {"id": "d4", "name": "오렌지주스", "price": 3000},
        {"id": "d5", "name": "물",         "price": 1000},
    ],
    "세트": [
        {"id": "set1", "name": "치즈버거 세트",  "price": 9500,  "includes": "치즈버거+감자튀김+음료"},
        {"id": "set2", "name": "더블버거 세트",  "price": 12000, "includes": "더블버거+감자튀김+음료"},
        {"id": "set3", "name": "베이컨버거 세트","price": 10500, "includes": "베이컨버거+감자튀김+음료"},
    ],
}

# 이름으로 빠르게 찾기 위한 플랫 맵 (add_to_cart 에서 사용)
MENU_BY_NAME: dict = {
    item["name"]: {**item, "category": cat}
    for cat, items in MENU_DATA.items()
    for item in items
}

# 별칭/구어체 → 정식 메뉴명 (STT 전사와 손님 구어 표현 흡수)
MENU_ALIASES: dict[str, str] = {
    "감튀": "감자튀김", "후렌치후라이": "감자튀김", "프렌치프라이": "감자튀김",
    "포테이토": "감자튀김", "튀김": "감자튀김",
    "코카콜라": "콜라", "코크": "콜라", "펩시": "콜라",
    "스프라이트": "사이다", "칠성사이다": "사이다",
    "쉬림프버거": "새우버거", "쉬림프": "새우버거",
    "불버거": "불고기버거", "불고기": "불고기버거",
    "베이컨": "베이컨버거",
    "텐더": "치킨텐더", "치킨": "치킨텐더",
    "어니언링": "양파링",
    "주스": "오렌지주스", "오렌지": "오렌지주스",
    "생수": "물",
}


def _norm(s: str) -> str:
    """비교용 정규화 — 공백/특수문자 제거."""
    return re.sub(r"[\s\W_]+", "", s)


# 퍼지 매칭용 정규화 이름 맵 (긴 이름 우선 매칭되도록 길이순 정렬)
_NORM_NAMES: list[tuple[str, str]] = sorted(
    ((_norm(n), n) for n in MENU_BY_NAME),
    key=lambda x: -len(x[0]),
)


def recommend_menu(category: Optional[str] = None) -> dict:
    """
    메뉴 추천 function call 핸들러.
    category 없으면 전체, 있으면 해당 카테고리만 반환.
    """
    if category and category in MENU_DATA:
        return {"category": category, "items": MENU_DATA[category]}
    return {"all": MENU_DATA}


def find_item(name: str) -> Optional[dict]:
    """
    메뉴 이름으로 아이템 조회. 없으면 None.
    매칭 순서: 정확 일치 → 별칭 → 부분 일치 → 퍼지(STT 오타 흡수, 예: 지즈버거→치즈버거).
    """
    name = (name or "").strip()
    if not name:
        return None
    # 1) 정확 일치
    if name in MENU_BY_NAME:
        return MENU_BY_NAME[name]
    # 2) 별칭 (정규화 후 비교; "감튀 세트" 같은 조합은 세트 여부 반영)
    n = _norm(name)
    if n in MENU_BY_NAME:
        return MENU_BY_NAME[n]
    alias_hit = MENU_ALIASES.get(name) or MENU_ALIASES.get(n)
    if alias_hit:
        # 별칭 + "세트" 조합이면 세트 메뉴 우선 시도
        if "세트" in name:
            set_item = MENU_BY_NAME.get(f"{alias_hit} 세트")
            if set_item:
                return set_item
        return MENU_BY_NAME[alias_hit]
    # 3) 부분 일치 (긴 이름 우선 — "치즈버거 세트"가 "치즈버거"보다 먼저)
    for norm_menu, menu_name in _NORM_NAMES:
        if n in norm_menu or norm_menu in n:
            return MENU_BY_NAME[menu_name]
    # 4) 퍼지 매칭 — STT 오타 흡수 (한 글자 오인식 등)
    close = difflib.get_close_matches(n, [nm for nm, _ in _NORM_NAMES], n=1, cutoff=0.65)
    if close:
        menu_name = next(mn for nm, mn in _NORM_NAMES if nm == close[0])
        return MENU_BY_NAME[menu_name]
    return None
