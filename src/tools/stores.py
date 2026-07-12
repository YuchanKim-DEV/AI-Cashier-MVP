"""
매장 데이터 + 위치(geofence) 로직.

시나리오: 손님이 우리 앱을 켜고 매장에 '입장'하면 그 매장 메뉴가 자동으로 뜬다.
실제 GPS는 아직 못 쓰므로 앱에서 위치를 시뮬레이션해서 보낸다.
주문/결제는 폰 위치가 매장 반경 안에 있어야만 가능 (geofence).

MVP: 매장 1곳(오투오버거). 메뉴는 menu.MENU_DATA 공용.
추후 매장별 메뉴/좌표는 STORES 에 추가만 하면 된다.
"""

import math
from typing import Optional

from src.tools.menu import MENU_DATA

# 시뮬레이션용 좌표 (서울 강남 근처 임의 지점). 실제 GPS 도입 시 이 값만 교체.
STORES: list[dict] = [
    {
        "id": "o2o-gangnam",
        "name": "오투오버거 강남점",
        "address": "서울 강남구 테헤란로 123",
        "lat": 37.498095,
        "lng": 127.027610,
        "radius_m": 20,           # 20m 안이면 '매장 안'으로 인정 (입장 감지 + 결제 게이트)
    },
]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 거리(미터)."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def get_store(store_id: str) -> Optional[dict]:
    return next((s for s in STORES if s["id"] == store_id), None)


def find_nearby(lat: float, lng: float) -> Optional[dict]:
    """폰 좌표 기준 반경 안에 있는 가장 가까운 매장. 없으면 None."""
    best, best_d = None, None
    for s in STORES:
        d = haversine_m(lat, lng, s["lat"], s["lng"])
        if d <= s["radius_m"] and (best_d is None or d < best_d):
            best, best_d = s, d
    if best is None:
        return None
    return {**best, "distance_m": round(best_d, 1)}


def check_at_store(store_id: str, lat: float, lng: float) -> dict:
    """폰 위치가 해당 매장 반경 안인지 검사. 주문/결제 전 게이트."""
    s = get_store(store_id)
    if not s:
        return {"ok": False, "reason": "store_not_found", "message": "매장을 찾을 수 없습니다."}
    d = haversine_m(lat, lng, s["lat"], s["lng"])
    inside = d <= s["radius_m"]
    return {
        "ok": inside,
        "reason": None if inside else "location_mismatch",
        "distance_m": round(d, 1),
        "radius_m": s["radius_m"],
        "message": (
            f"{s['name']} 매장 안입니다. (약 {round(d)}m)"
            if inside else
            f"매장에서 약 {round(d)}m 떨어져 있어요. 매장 안에서만 주문/결제가 가능합니다."
        ),
    }


def store_menu(store_id: str) -> dict:
    """매장 메뉴 (MVP: 공용 MENU_DATA)."""
    return MENU_DATA
