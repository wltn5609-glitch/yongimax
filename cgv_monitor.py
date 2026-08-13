"""
CGV 용산아이파크몰 IMAX '오디세이' 예매 오픈 감지 & ntfy 푸시 알림 스크립트

하는 일:
- 오늘부터 DAYS_AHEAD일치 날짜를 하루씩 CGV 공개 스케줄 API로 조회
- 예전엔 없던 날짜에 회차가 새로 뜨면 -> ntfy로 폰에 푸시 알림
- 상태는 state.json에 저장 (GitHub Actions에서는 커밋으로 유지됨)

주의:
- 이 스크립트는 '조회'만 합니다. 좌석 선택이나 결제는 절대 하지 않아요.
  새 회차가 뜬 걸 알려줄 뿐, 실제 예매는 알림 받은 사람이 직접 CGV 앱/사이트에서 해야 해요.
- 영화가 바뀌거나 극장을 바꾸고 싶으면 아래 설정값만 바꾸면 됩니다.
"""

import json
import os
from datetime import datetime, timedelta

import requests

# ---------------- 설정 ----------------
CO_CD = "A420"
SITE_NO = "0013"          # CGV 용산아이파크몰. 다른 지점이면 이 코드만 바꾸면 됨
MOV_NO = "30001323"       # '오디세이' 영화 코드(movNo). 다른 영화면 이 값을 바꿔야 함
TARGET_SCNS_NO = "018"    # IMAX관 코드(scnsNo). 전체 상영관 다 보고 싶으면 None으로
DAYS_AHEAD = 21           # 오늘부터 며칠 뒤까지 확인할지
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()

HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.5 Safari/605.1.15"
    ),
    "Referer": "https://cgv.co.kr/cnm/movieBook/movie",
}

API_URL = "https://cgv.co.kr/api/v1/booking/searchSchByMov"


def fetch_schedule(ymd: str):
    """특정 날짜(YYYYMMDD)의 상영 스케줄을 조회. 실패하면 빈 리스트 반환."""
    params = {
        "coCd": CO_CD,
        "siteNo": SITE_NO,
        "scnYmd": ymd,
        "movNo": MOV_NO,
        "rtctlScopCd": "08",
    }
    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data") or []
    except Exception as e:
        print(f"[경고] {ymd} 조회 실패: {e}")
        return None  # None = 조회 자체가 실패한 것 (사이트 점검/차단 등), 빈 리스트와 구분


def send_ntfy(title: str, message: str):
    if not NTFY_TOPIC:
        print("[알림 생략] NTFY_TOPIC이 설정 안 되어 있어요.")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title.encode("utf-8"),
                "Priority": "urgent",
                "Tags": "movie_camera,rotating_light",
            },
            timeout=10,
        )
        print(f"[알림 발송] {title}")
    except Exception as e:
        print(f"[경고] ntfy 발송 실패: {e}")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    state = load_state()
    today = datetime.now()

    for i in range(DAYS_AHEAD):
        d = today + timedelta(days=i)
        ymd = d.strftime("%Y%m%d")

        items = fetch_schedule(ymd)
        if items is None:
            # 조회 자체가 실패한 날은 상태를 건드리지 않고 넘어감 (오탐 방지)
            continue

        if TARGET_SCNS_NO:
            items = [it for it in items if it.get("scnsNo") == TARGET_SCNS_NO]

        was_open = state.get(ymd, {}).get("open", False)
        is_open = len(items) > 0

        if is_open and not was_open:
            times = ", ".join(sorted(it.get("scnsrtTm", "") for it in items))
            date_label = f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})"
            send_ntfy(
                title=f"🎬 용아맥 {date_label} 예매 오픈!",
                message=f"회차: {times}\n지금 바로 CGV 앱으로! (https://cgv.co.kr/cnm/movieBook/movie)",
            )

        state[ymd] = {
            "open": is_open,
            "session_count": len(items),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    save_state(state)


if __name__ == "__main__":
    main()
