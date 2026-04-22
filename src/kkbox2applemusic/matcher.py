"""透過 iTunes Search API 或 Apple Music API 將 KKBOX 歌曲比對到 Apple Music。"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from .parser import Song

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
APPLE_MUSIC_SEARCH_URL = "https://api.music.apple.com/v1/catalog/{country}/search"

_RATE_LIMIT_DELAY = 0.5   # 秒，避免被 API 限流
_MIN_CONFIDENCE = 0.42    # 最低信心門檻（低於此值視為錯誤比對）

# 需要從歌名中移除的影視/版本標注關鍵字
_MEDIA_KEYWORDS = frozenset([
    "電影", "影片", "影集", "電視劇", "劇集", "影视剧", "电视剧",
    "主題曲", "插曲", "片頭曲", "片頭", "片尾曲", "片尾",
    "心動曲", "原唱", "幸福版", "再見版", "音樂產房",
    "動畫劇集", "三立戲劇", "TVBS連續劇", "星宇航空",
])

# 括號內應保留（屬於歌名本身）的模式
_KEEP_PAREN_RE = re.compile(
    r"feat\.|ft\.|1000 Times|\d|跳樓機|若是", re.IGNORECASE
)
# 符合影視後綴的 " - ..." 模式
_MEDIA_SUFFIX_RE = re.compile(
    r"\s*[-–—]\s*(?:" + "|".join(re.escape(k) for k in _MEDIA_KEYWORDS) + r")[^-–—]*$"
)
# Version 後綴（JOLIN Version/...）
_VERSION_SUFFIX_RE = re.compile(r"\s*[-–—]\s*\w+\s*[Vv]ersion.*$")
# Live 後綴（座位 - Live）
_LIVE_SUFFIX_RE = re.compile(r"\s*[-–—]\s*Live\s*$", re.IGNORECASE)


@dataclass
class MatchResult:
    song: Song
    matched: bool
    apple_track_id: int | None = None
    apple_track_name: str | None = None
    apple_artist: str | None = None
    apple_album: str | None = None
    apple_url: str | None = None   # trackViewUrl，可在瀏覽器開啟
    confidence: float = 0.0


def _strip_song_name(name: str) -> str:
    """移除 KKBOX 歌名中的影視/版本標注，保留核心歌名。

    Examples:
        "幸福在歌唱 - 電影《陽光女子合唱團》幸福版主題曲" → "幸福在歌唱"
        "孤單心事-音樂產房(原唱:藍又時)(Live)"           → "孤單心事"
        "聖誕星 (feat. 楊瑞代)"                         → "聖誕星 (feat. 楊瑞代)"（保留）
    """
    result = name

    def _maybe_remove_paren(m: re.Match) -> str:
        content = m.group(1)
        if _KEEP_PAREN_RE.search(content):
            return m.group(0)
        if any(kw in content for kw in _MEDIA_KEYWORDS):
            return ""
        # 全為中文且較長：可能是副標，嘗試移除
        if len(content) > 8 and re.fullmatch(r"[\u4e00-\u9fff\s《》〈〉【】，、／]+", content):
            return ""
        return m.group(0)

    result = re.sub(r"\s*[（(]([^）)]+)[）)]\s*", _maybe_remove_paren, result)
    result = _MEDIA_SUFFIX_RE.sub("", result)
    result = _VERSION_SUFFIX_RE.sub("", result)
    result = _LIVE_SUFFIX_RE.sub("", result)
    result = re.sub(r"\s*[-–—]\s*音樂產房.*$", "", result)

    return result.strip()


def _artist_variants(artist: str) -> list[str]:
    """從 KKBOX 藝人名稱產生搜尋變體。

    Examples:
        "周杰倫 (Jay Chou)"    → ["周杰倫 (Jay Chou)", "Jay Chou", "周杰倫"]
        "G.E.M. 鄧紫棋"        → ["G.E.M. 鄧紫棋", "G.E.M.", "鄧紫棋"]
        "蕭秉治Xiao Bing Chih" → ["蕭秉治Xiao Bing Chih", "蕭秉治", "Xiao Bing Chih"]
        "Various Artists"      → [""]  （改以純歌名搜尋）
    """
    if artist in ("Various Artists", "群星", ""):
        return [""]

    variants: list[str] = [artist]

    # "中文 (English)" 格式
    paren = re.search(r"\(([^)]+)\)", artist)
    if paren:
        eng = paren.group(1).strip()
        zh = re.sub(r"\s*\([^)]*\)\s*", "", artist).strip()
        for v in (eng, zh):
            if v and v not in variants:
                variants.append(v)
    else:
        # 拆 ASCII 與中文部分（無括號格式，如 "蕭秉治Xiao Bing Chih"）
        ascii_part = re.sub(r"[^\x00-\x7f,\s]+", "", artist).strip(" ,")
        cjk_part = re.sub(r"[\x00-\x7f]+", "", artist).strip()
        if ascii_part and len(ascii_part) > 1 and ascii_part not in variants:
            variants.append(ascii_part)
        if cjk_part and cjk_part not in variants:
            variants.append(cjk_part)

    # 多位藝人：取第一位
    first = re.split(r"[,，&]", artist)[0].strip()
    if first and first != artist and first not in variants:
        variants.append(first)

    return variants


def _similarity(a: str, b: str) -> float:
    """計算兩字串相似度（0.0 ~ 1.0）。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _name_score(search_name: str, result_name: str) -> float:
    """計算歌名相似度，加入子字串加分機制。"""
    sim = _similarity(search_name, result_name)
    sn, rn = search_name.lower(), result_name.lower()
    if sn and (rn.startswith(sn) or sn.startswith(rn) or sn in rn or rn in sn):
        sim = max(sim, 0.85)
    return sim


# 非原始版本的關鍵字：當原始歌名不含這些詞，但比對結果含有時，降低分數
_NON_ORIGINAL_RE = re.compile(
    r"\b(韓文版|Japanese Ver|English Ver|Remix|Instrumental|Karaoke|Acoustic)\b",
    re.IGNORECASE,
)


def _score_candidate(search_name: str, original_artist: str, candidate: dict) -> float:
    """根據歌名與藝人（含所有變體）計算最佳比對分數。"""
    result_name = candidate.get("trackName", "")
    result_artist = candidate.get("artistName", "")

    n_score = _name_score(search_name, result_name)

    if original_artist:
        a_score = max(
            _similarity(v, result_artist) for v in _artist_variants(original_artist)
        )
    else:
        a_score = 0.5  # 無藝人（Various Artists）給中性分

    score = n_score * 0.65 + a_score * 0.35

    # 若搜尋歌名不含非原始版本關鍵字，但比對結果含有，則降低分數
    if _NON_ORIGINAL_RE.search(result_name) and not _NON_ORIGINAL_RE.search(search_name):
        score *= 0.7

    return score


async def _search_itunes(
    term: str, client: httpx.AsyncClient, country: str, limit: int
) -> list[dict]:
    """呼叫 iTunes Search API，失敗時回傳空列表。"""
    if not term.strip():
        return []
    try:
        response = await client.get(
            ITUNES_SEARCH_URL,
            params={"term": term, "entity": "song", "country": country, "limit": limit},
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        return []


async def _search_apple_music(
    term: str,
    client: httpx.AsyncClient,
    country: str,
    limit: int,
    dev_token: str,
) -> list[dict]:
    """呼叫 Apple Music API catalog search，結果正規化為與 iTunes API 相同格式。

    Apple Music API 回傳格式：
        results.songs.data[].attributes.{name, artistName, albumName, url}
    """
    if not term.strip():
        return []
    url = APPLE_MUSIC_SEARCH_URL.format(country=country)
    try:
        response = await client.get(
            url,
            params={"term": term, "types": "songs", "limit": limit},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
        response.raise_for_status()
        data = response.json()
        songs_data = data.get("results", {}).get("songs", {}).get("data", [])
        # 正規化為 iTunes API 格式，方便共用 _score_candidate
        normalized = []
        for item in songs_data:
            attrs = item.get("attributes", {})
            normalized.append({
                "trackId": int(item.get("id", 0)),
                "trackName": attrs.get("name", ""),
                "artistName": attrs.get("artistName", ""),
                "collectionName": attrs.get("albumName", ""),
                "trackViewUrl": attrs.get("url", ""),
            })
        return normalized
    except (httpx.HTTPError, ValueError):
        return []


async def _search(
    term: str,
    client: httpx.AsyncClient,
    country: str,
    limit: int,
    dev_token: str | None = None,
) -> list[dict]:
    """搜尋歌曲：有 dev_token 時用 Apple Music API，否則用 iTunes Search API。"""
    if dev_token:
        return await _search_apple_music(term, client, country, limit, dev_token)
    return await _search_itunes(term, client, country, limit)


async def match_song(
    song: Song,
    client: httpx.AsyncClient,
    country: str = "tw",
    limit: int = 5,
    dev_token: str | None = None,
) -> MatchResult:
    """多策略搜尋，取最佳比對結果。

    搜尋順序：
    1. 核心歌名 + 各藝人變體
    2. 原始歌名 + 各藝人變體（若與策略1不同）
    3. 核心歌名（無藝人，適用 Various Artists）
    找到信心分數 ≥ 0.8 時提前結束。
    """
    stripped = _strip_song_name(song.name)
    artist_vars = _artist_variants(song.artist)

    # 建立 (search_name, artist_for_query) 清單
    queries: list[tuple[str, str]] = []
    for av in artist_vars:
        queries.append((stripped, av))
    if stripped != song.name:
        for av in artist_vars:
            queries.append((song.name, av))
    queries.append((stripped, ""))  # 純歌名回退

    seen: set[str] = set()
    best_candidate: dict | None = None
    best_score = 0.0

    for search_name, artist_q in queries:
        term = f"{search_name} {artist_q}".strip() if artist_q else search_name
        if term in seen:
            continue
        seen.add(term)

        candidates = await _search(term, client, country, limit, dev_token)
        for c in candidates:
            score = _score_candidate(search_name, song.artist, c)
            if score > best_score:
                best_score = score
                best_candidate = c

        if best_score >= 0.8:
            break

    if best_candidate is None or best_score < _MIN_CONFIDENCE:
        return MatchResult(song=song, matched=False, confidence=best_score)

    return MatchResult(
        song=song,
        matched=True,
        apple_track_id=best_candidate.get("trackId"),
        apple_track_name=best_candidate.get("trackName"),
        apple_artist=best_candidate.get("artistName"),
        apple_album=best_candidate.get("collectionName"),
        apple_url=best_candidate.get("trackViewUrl"),
        confidence=best_score,
    )


async def match_all(
    songs: list[Song],
    country: str = "tw",
    on_progress: object = None,
    dev_token: str | None = None,
) -> list[MatchResult]:
    """依序比對所有歌曲，每首之間加入 rate limit 延遲。"""
    results: list[MatchResult] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i, song in enumerate(songs):
            if i > 0:
                await asyncio.sleep(_RATE_LIMIT_DELAY)
            result = await match_song(song, client, country=country, dev_token=dev_token)
            results.append(result)
            if on_progress is not None:
                on_progress(result)
    return results
