"""
결정적 의도 라우터 (fast-path) — 핵심 주문 흐름을 LLM 없이 즉시 처리.

4GB 저사양 하드웨어 대응:
  - "치즈버거 하나랑 콜라 주세요" 같은 명확한 주문은 규칙+퍼지매칭으로 0.1초 내 처리
  - LLM 추론(1~3초) 생략 → 지연/메모리 부담 감소, 규칙 기반이라 할루시네이션 0
  - 애매한 발화(질문, 잡담, 복합 요청)는 None 반환 → LLM 폴백

parse(text) -> dict | None
  {"intent": "add",            "items": [(메뉴명, 수량), ...]}
  {"intent": "remove",         "items": [(메뉴명, 1), ...]}
  {"intent": "checkout"}
  {"intent": "select_payment", "method": "app_card"|"physical_card"}
  {"intent": "view_cart"}
  {"intent": "recommend",      "category": str|None}
  None  → LLM 폴백
"""

import re
from typing import Optional

from src.tools.menu import MENU_DATA, MENU_ALIASES, find_item, _norm

# 메뉴명 + 별칭을 길이순(긴 것 우선)으로 — "치즈버거 세트"가 "치즈버거"보다 먼저 매칭
_MENU_TERMS: list[str] = sorted(
    [it["name"] for items in MENU_DATA.values() for it in items] + list(MENU_ALIASES),
    key=len, reverse=True,
)

_QTY_WORDS = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "다섯": 5}
_SEG_SPLIT = re.compile(r"이랑|랑|하고|그리고|및|,")
_REMOVE_RE = re.compile(r"빼|취소|제거|지워|삭제")
_QUESTION_RE = re.compile(r"있어요|있나요|있을까|인가요|뭐가|무엇|어떤|어때")   # '얼마'는 view_cart 가 처리
_ORDER_WORDS = re.compile(r"주세요|주문|추가|담아|먹을게|할게요|하나|한개|두개|세개|\d+개|개|요$|줘|요\b")
_PAY_APP_RE = re.compile(r"앱\s*카드")
_PAY_PHYS_RE = re.compile(r"현장\s*카드|실물\s*카드|일반\s*카드")
_CHECKOUT_RE = re.compile(r"(결제|계산)\s*(할|해|하|부탁|이요|요)|주문\s*(끝|완료|마무리)|다\s*(됐|골랐)")
_VIEW_RE = re.compile(r"(장바구니|주문\s*내역|담은\s*거|뭐\s*담)|(지금\s*)?(총\s*)?얼마")
_RECOMMEND_RE = re.compile(r"추천|인기|맛있는\s*거|뭐가\s*맛있")


def _find_qty(segment: str) -> int:
    """세그먼트에서 수량 추출 (없으면 1)."""
    m = re.search(r"(\d+)\s*(개|잔|인분)?", segment)
    if m and m.group(1):
        n = int(m.group(1))
        if 1 <= n <= 20:
            return n
    for w, n in _QTY_WORDS.items():
        # 수량 단어는 '개/잔' 동반 또는 관용형("하나 주세요")만 인정 — '네'(=yes) 오인 방지
        if re.search(rf"{w}\s*(개|잔|인분)", segment) or (w in ("하나", "둘") and w in segment):
            return n
    return 1


def _extract_items(text: str) -> list[tuple[str, int]]:
    """문장에서 (정식 메뉴명, 수량) 목록 추출. 긴 이름 우선, 매칭 구간 소비."""
    items: list[tuple[str, int]] = []
    for seg in _SEG_SPLIT.split(text):
        seg_norm = _norm(seg)
        if not seg_norm:
            continue
        consumed = seg_norm
        matched = False
        for term in _MENU_TERMS:
            t_norm = _norm(term)
            if t_norm and t_norm in consumed:
                item = find_item(term)
                if item:
                    items.append((item["name"], _find_qty(seg)))
                    matched = True
                consumed = consumed.replace(t_norm, "", 1)  # 소비 → "치즈버거 세트" 후 "치즈버거" 중복 방지
                break  # 세그먼트당 1개 (…랑 …로 분리되므로)
        if not matched:
            # 정확 매칭 실패 → 주문 단어 제거 후 퍼지 매칭 (STT 오타: 지즈버거 세트 → 치즈버거 세트)
            cleaned = _ORDER_WORDS.sub("", seg).strip()
            if len(_norm(cleaned)) >= 3:
                item = find_item(cleaned)
                if item:
                    items.append((item["name"], _find_qty(seg)))
    return items


def parse(text: str) -> Optional[dict]:
    """발화 → 의도. 확신 없으면 None (LLM 폴백)."""
    t = (text or "").strip()
    if not t or len(t) > 60:          # 긴 발화 = 복합 요청 가능성 → LLM
        return None

    # 질문형(재고/추천 문의 등)은 자연스러운 응대가 필요 → LLM (추천 요청만 예외)
    if _QUESTION_RE.search(t) and not _RECOMMEND_RE.search(t):
        return None

    # 1) 결제 수단 (checkout 패턴보다 먼저 — "앱카드로 결제할게요")
    if _PAY_APP_RE.search(t):
        return {"intent": "select_payment", "method": "app_card"}
    if _PAY_PHYS_RE.search(t):
        return {"intent": "select_payment", "method": "physical_card"}

    items = _extract_items(t)

    # 2) 메뉴 빼기
    if _REMOVE_RE.search(t):
        return {"intent": "remove", "items": [(n, 1) for n, _ in items]} if items else None

    # 3) 추천
    if _RECOMMEND_RE.search(t):
        cat = next((c for c in MENU_DATA if c in t), None)
        return {"intent": "recommend", "category": cat}

    # 4) 결제/계산 (메뉴 언급 없이)
    if _CHECKOUT_RE.search(t) and not items:
        return {"intent": "checkout"}

    # 5) 장바구니 확인
    if _VIEW_RE.search(t) and not items:
        return {"intent": "view_cart"}

    # 6) 메뉴 담기 — 메뉴가 있고 부정어가 없으면 주문으로 간주
    if items:
        return {"intent": "add", "items": items}

    return None   # 파악 불가 → LLM


# ─── 응답 템플릿 (규칙 기반이라 항상 사실만 말함) ────────────────────────────
def response_for(intent: dict, results: list[dict], channel: str = "kiosk") -> str:
    """fast-path 실행 결과 → 손님에게 할 말 (한국어). channel: kiosk | app."""
    kind = intent["intent"]
    if kind == "add":
        ok = [r for r in results if r.get("success")]
        bad = [r for r in results if not r.get("success")]
        parts = []
        if ok:
            names = ", ".join(f"{r['item']['name']} {r['item']['quantity']}개" if r.get("action") == "added"
                              else f"{r['item']['name']} {r['item']['quantity']}개" for r in ok)
            parts.append(f"네! {names} 담아드렸어요~")
        if bad:
            parts.append("일부 메뉴는 저희 메뉴에 없어서 못 담았어요.")
        parts.append("더 필요하신 거 있으세요?")
        return " ".join(parts)
    if kind == "remove":
        ok = [r.get("removed") for r in results if r.get("success")]
        if ok:
            return f"{', '.join(ok)} 빼드렸어요! 다른 건 괜찮으세요?"
        return "앗, 장바구니에 그 메뉴가 없어요!"
    if kind == "checkout":
        r = results[0] if results else {}
        if r.get("success"):
            total = r.get("cart", {}).get("total", 0)
            if channel == "app":
                # 앱: 수단 선택 없음 — 장바구니 확인 + 결제 버튼 안내만
                return f"총 {total:,}원이에요! 장바구니 확인하시고, 아래 결제 버튼을 눌러주세요~"
            return f"주문 확인해드릴게요, 총 {total:,}원이에요! 앱카드 또는 현장카드 중 어떻게 결제하시겠어요?"
        return "아직 장바구니가 비어있어요! 메뉴 먼저 담아주세요~"
    if kind == "select_payment":
        r = results[0] if results else {}
        if r.get("error") == "speaker_mismatch":
            return r.get("message", "주문하신 분이 직접 말씀해 주셔야 결제가 가능해요.")
        if channel == "app":
            return "네, 등록된 앱카드로 결제하겠습니다!"
        label = "앱카드" if intent.get("method") == "app_card" else "현장카드"
        return f"네, {label}로 결제 도와드릴게요!"
    if kind == "view_cart":
        r = results[0] if results else {}
        items = r.get("items", [])
        if not items:
            return "아직 장바구니가 비어있어요!"
        names = ", ".join(f"{i['name']} {i['quantity']}개" for i in items)
        return f"지금 {names}, 총 {r.get('total', 0):,}원이에요!"
    if kind == "recommend":
        cat = intent.get("category")
        if cat and cat in MENU_DATA:
            top = MENU_DATA[cat][0]
            return f"{cat} 중엔 {top['name']}({top['price']:,}원)가 인기예요! 담아드릴까요?"
        return "저희 인기 메뉴는 치즈버거 세트예요! 버거, 감자튀김, 음료까지 9,500원이에요. 담아드릴까요?"
    return ""
