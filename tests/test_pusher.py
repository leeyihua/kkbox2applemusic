"""測試 Apple Music API 推送邏輯。"""

import pytest
import respx
import httpx

from kkbox2applemusic.matcher import MatchResult
from kkbox2applemusic.parser import Song
from kkbox2applemusic.pusher import push_to_apple_music

DEV_TOKEN = "fake_dev_token"
USER_TOKEN = "fake_user_token"

_SONG = Song(name="晴天", artist="周杰倫", album="葉惠美", kkbox_id="1", track_id="x")

_MATCHED = MatchResult(
    song=_SONG, matched=True,
    apple_track_id=209908499, apple_track_name="晴天",
    apple_artist="Jay Chou", apple_album="葉惠美", confidence=0.95,
)
_UNMATCHED = MatchResult(song=_SONG, matched=False)

_LIST_URL = "https://api.music.apple.com/v1/me/library/playlists"
_CREATE_URL = "https://api.music.apple.com/v1/me/library/playlists"

_LIST_WITH_MATCH = {
    "data": [{"id": "p.OLD", "attributes": {"name": "測試播放清單"}}]
}
_LIST_EMPTY = {"data": []}


def _tracks_url(pid: str) -> str:
    return f"https://api.music.apple.com/v1/me/library/playlists/{pid}/tracks"

def _delete_url(pid: str) -> str:
    return f"https://api.music.apple.com/v1/me/library/playlists/{pid}"


# ── conflict="new"（預設）──────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_push_creates_playlist_and_adds_tracks():
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.ABC123"}]})
    )
    respx.post(_tracks_url("p.ABC123")).mock(return_value=httpx.Response(204))

    playlist_id, success, failed = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN
    )

    assert playlist_id == "p.ABC123"
    assert success == 1
    assert failed == 0


@pytest.mark.asyncio
@respx.mock
async def test_push_skips_unmatched():
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.XYZ"}]})
    )
    respx.post(_tracks_url("p.XYZ")).mock(return_value=httpx.Response(204))

    _playlist_id, success, failed = await push_to_apple_music(
        [_MATCHED, _UNMATCHED], "播放清單", DEV_TOKEN, USER_TOKEN
    )

    assert success == 1
    assert failed == 0


@pytest.mark.asyncio
@respx.mock
async def test_push_counts_failed_batch():
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.ERR"}]})
    )
    respx.post(_tracks_url("p.ERR")).mock(return_value=httpx.Response(400))

    _playlist_id, success, failed = await push_to_apple_music(
        [_MATCHED], "播放清單", DEV_TOKEN, USER_TOKEN
    )

    assert success == 0
    assert failed == 1


@pytest.mark.asyncio
@respx.mock
async def test_push_calls_progress_callback():
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.CB"}]})
    )
    respx.post(_tracks_url("p.CB")).mock(return_value=httpx.Response(204))

    calls: list[tuple[int, int]] = []
    await push_to_apple_music(
        [_MATCHED], "播放清單", DEV_TOKEN, USER_TOKEN,
        on_progress=lambda ok, fail: calls.append((ok, fail)),
    )

    assert len(calls) == 1
    assert calls[0] == (1, 0)


@pytest.mark.asyncio
@respx.mock
async def test_push_raises_on_playlist_creation_error():
    respx.post(_CREATE_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(httpx.HTTPStatusError):
        await push_to_apple_music([_MATCHED], "播放清單", DEV_TOKEN, USER_TOKEN)


# ── conflict="replace" ────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_replace_deletes_old_and_creates_new():
    """replace 模式：找到舊清單 → 刪除 → 建立新清單 → 加入歌曲。"""
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_LIST_WITH_MATCH))
    respx.delete(_delete_url("p.OLD")).mock(return_value=httpx.Response(204))
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.NEW"}]})
    )
    respx.post(_tracks_url("p.NEW")).mock(return_value=httpx.Response(204))

    playlist_id, success, _ = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN, conflict="replace"
    )

    assert playlist_id == "p.NEW"
    assert success == 1


@pytest.mark.asyncio
@respx.mock
async def test_replace_creates_new_when_not_found():
    """replace 模式：找不到舊清單 → 直接建立新清單。"""
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_LIST_EMPTY))
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.FRESH"}]})
    )
    respx.post(_tracks_url("p.FRESH")).mock(return_value=httpx.Response(204))

    playlist_id, success, _ = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN, conflict="replace"
    )

    assert playlist_id == "p.FRESH"
    assert success == 1


# ── conflict="append" ─────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_append_adds_to_existing():
    """append 模式：找到現有清單 → 直接加入歌曲（不建立新清單）。"""
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_LIST_WITH_MATCH))
    respx.post(_tracks_url("p.OLD")).mock(return_value=httpx.Response(204))

    playlist_id, success, _ = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN, conflict="append"
    )

    assert playlist_id == "p.OLD"
    assert success == 1


@pytest.mark.asyncio
@respx.mock
async def test_append_creates_new_when_not_found():
    """append 模式：找不到現有清單 → 建立新清單。"""
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_LIST_EMPTY))
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.APPENDED"}]})
    )
    respx.post(_tracks_url("p.APPENDED")).mock(return_value=httpx.Response(204))

    playlist_id, success, _ = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN, conflict="append"
    )

    assert playlist_id == "p.APPENDED"
    assert success == 1


@pytest.mark.asyncio
@respx.mock
async def test_find_playlist_paginates():
    """搜尋清單時應跟隨 next 分頁直到找到目標。"""
    page1 = {
        "data": [{"id": "p.OTHER", "attributes": {"name": "其他清單"}}],
        "next": "/v1/me/library/playlists?offset=1",
    }
    page2 = {
        "data": [{"id": "p.TARGET", "attributes": {"name": "測試播放清單"}}],
    }
    responses = iter([
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ])
    respx.get(_LIST_URL).mock(side_effect=lambda _req: next(responses))
    respx.post(_tracks_url("p.TARGET")).mock(return_value=httpx.Response(204))

    playlist_id, success, _ = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN, conflict="append"
    )

    assert playlist_id == "p.TARGET"
    assert success == 1
