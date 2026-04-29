"""從 KKBOX 排行榜網頁抓取歌曲清單。"""

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import httpx

from .parser import Song

_TITLE_RE = re.compile(r"<title>([^<]+)</title>")

# KKBOX 排行榜 API 基礎 URL，不需要認證
_CHART_API_BASE = "https://kma.kkbox.com/charts/api/v1"

# 各類型排行榜的最大筆數（來自 KKBOX 前端 JS）
_PERIOD_LIMITS = {"daily": 50, "weekly": 100, "yearly": 100}


async def fetch_chart_songs(url: str) -> tuple[str, list[Song]]:
    """從 KKBOX 排行榜網頁抓取歌曲清單，回傳 (排行榜名稱, 歌曲清單)。

    解析 URL 路徑取得排行榜類型（yearly/weekly/daily）與歌曲分類，
    呼叫 KKBOX 公開 API 取得歌曲。
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        # 抓取 HTML 取得排行榜顯示名稱
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text

        title_m = _TITLE_RE.search(html)
        playlist_name = title_m.group(1).split(" - ")[0].strip() if title_m else "KKBOX 排行榜"

        # 從 URL 路徑解析排行榜類型與分類
        # 例：/charts/yearly/newrelease → period=yearly, category=newrelease
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")  # ['charts', 'yearly', 'newrelease']
        period = path_parts[1] if len(path_parts) > 1 else "daily"
        category = path_parts[2] if len(path_parts) > 2 else "newrelease"
        qs = parse_qs(parsed.query)
        lang = qs.get("lang", ["tc"])[0]
        terr = qs.get("terr", ["tw"])[0]
        limit = _PERIOD_LIMITS.get(period, 100)

        # 組合 API 參數；daily 需要 date（昨天，當日資料未就緒）
        params: dict[str, str | int] = {
            "lang": lang,
            "terr": terr,
            "type": category,
            "limit": limit,
        }
        if period == "daily":
            params["date"] = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 呼叫 KKBOX 公開排行榜 API（不需要認證）
        api_url = f"{_CHART_API_BASE}/{period}"
        chart_resp = await client.get(
            api_url, params=params, headers={"User-Agent": "Mozilla/5.0"}
        )
        chart_resp.raise_for_status()
        data = chart_resp.json()

        # 回應結構：{data: {charts: {newrelease: [...], ...}}}
        charts: dict = data.get("data", {}).get("charts", {})
        if not charts:
            raise RuntimeError("API 回應中找不到排行榜資料，結構可能已變更")

        # 取指定分類；若無則取第一個分類
        items = charts.get(category) or next(iter(charts.values()), [])

        songs: list[Song] = []
        for item in items:
            if item.get("type") == "album":
                continue
            songs.append(
                Song(
                    name=item.get("song_name", ""),
                    artist=item.get("artist_roles", ""),
                    album=item.get("album_name", ""),
                    kkbox_id=item.get("song_id", ""),
                    track_id="",
                )
            )

        return playlist_name, songs
