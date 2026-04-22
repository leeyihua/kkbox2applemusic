"""透過 Apple Music API 直接將播放清單推送至使用者帳號。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from .matcher import MatchResult

_API_BASE = "https://api.music.apple.com"
_BATCH_SIZE = 100  # Apple Music API 每次最多加入 100 首


def _headers(dev_token: str, user_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {dev_token}",
        "Music-User-Token": user_token,
        "Content-Type": "application/json",
    }


async def _create_playlist(
    name: str,
    description: str,
    dev_token: str,
    user_token: str,
    client: httpx.AsyncClient,
) -> str:
    """在使用者資料庫建立新播放清單，回傳 playlist id。"""
    resp = await client.post(
        f"{_API_BASE}/v1/me/library/playlists",
        headers=_headers(dev_token, user_token),
        json={"attributes": {"name": name, "description": description}},
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["id"]


async def _add_tracks(
    playlist_id: str,
    track_ids: list[str],
    dev_token: str,
    user_token: str,
    client: httpx.AsyncClient,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    """批次將 Apple Music catalog 歌曲加入播放清單。

    回傳 (成功數, 失敗數)。
    """
    success = 0
    failed = 0

    for i in range(0, len(track_ids), _BATCH_SIZE):
        batch = track_ids[i : i + _BATCH_SIZE]
        resp = await client.post(
            f"{_API_BASE}/v1/me/library/playlists/{playlist_id}/tracks",
            headers=_headers(dev_token, user_token),
            json={"data": [{"id": tid, "type": "songs"} for tid in batch]},
        )
        if resp.status_code == 204:  # No Content = 成功
            success += len(batch)
        else:
            failed += len(batch)

        if on_progress:
            on_progress(success, failed)

        if i + _BATCH_SIZE < len(track_ids):
            await asyncio.sleep(0.3)

    return success, failed


async def push_to_apple_music(
    results: list[MatchResult],
    playlist_name: str,
    dev_token: str,
    user_token: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[str, int, int]:
    """建立播放清單並批次加入比對成功的歌曲。

    Args:
        results:       match_all() 的輸出
        playlist_name: 播放清單名稱
        dev_token:     Apple Music Developer Token
        user_token:    Music User Token（代表使用者帳號）
        on_progress:   進度回呼 (成功數, 失敗數)

    Returns:
        (playlist_id, 成功數, 失敗數)

    Raises:
        httpx.HTTPStatusError: API 呼叫失敗（含 401 未授權、403 無訂閱等）
    """
    matched = [r for r in results if r.matched and r.apple_track_id]
    track_ids = [str(r.apple_track_id) for r in matched]

    async with httpx.AsyncClient(timeout=30.0) as client:
        playlist_id = await _create_playlist(
            name=playlist_name,
            description=f"從 KKBOX 匯入，共 {len(matched)} 首",
            dev_token=dev_token,
            user_token=user_token,
            client=client,
        )
        success, failed = await _add_tracks(
            playlist_id=playlist_id,
            track_ids=track_ids,
            dev_token=dev_token,
            user_token=user_token,
            client=client,
            on_progress=on_progress,
        )

    return playlist_id, success, failed
