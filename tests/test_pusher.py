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


@pytest.mark.asyncio
@respx.mock
async def test_push_creates_playlist_and_adds_tracks():
    # 模擬建立播放清單
    respx.post("https://api.music.apple.com/v1/me/library/playlists").mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.ABC123"}]})
    )
    # 模擬加入歌曲
    respx.post(
        "https://api.music.apple.com/v1/me/library/playlists/p.ABC123/tracks"
    ).mock(return_value=httpx.Response(204))

    playlist_id, success, failed = await push_to_apple_music(
        [_MATCHED], "測試播放清單", DEV_TOKEN, USER_TOKEN
    )

    assert playlist_id == "p.ABC123"
    assert success == 1
    assert failed == 0


@pytest.mark.asyncio
@respx.mock
async def test_push_skips_unmatched():
    respx.post("https://api.music.apple.com/v1/me/library/playlists").mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.XYZ"}]})
    )
    respx.post(
        "https://api.music.apple.com/v1/me/library/playlists/p.XYZ/tracks"
    ).mock(return_value=httpx.Response(204))

    _playlist_id, success, failed = await push_to_apple_music(
        [_MATCHED, _UNMATCHED], "播放清單", DEV_TOKEN, USER_TOKEN
    )

    assert success == 1   # 只有 _MATCHED 被推送
    assert failed == 0


@pytest.mark.asyncio
@respx.mock
async def test_push_counts_failed_batch():
    respx.post("https://api.music.apple.com/v1/me/library/playlists").mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.ERR"}]})
    )
    respx.post(
        "https://api.music.apple.com/v1/me/library/playlists/p.ERR/tracks"
    ).mock(return_value=httpx.Response(400))  # 模擬批次失敗

    _playlist_id, success, failed = await push_to_apple_music(
        [_MATCHED], "播放清單", DEV_TOKEN, USER_TOKEN
    )

    assert success == 0
    assert failed == 1


@pytest.mark.asyncio
@respx.mock
async def test_push_calls_progress_callback():
    respx.post("https://api.music.apple.com/v1/me/library/playlists").mock(
        return_value=httpx.Response(201, json={"data": [{"id": "p.CB"}]})
    )
    respx.post(
        "https://api.music.apple.com/v1/me/library/playlists/p.CB/tracks"
    ).mock(return_value=httpx.Response(204))

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
    respx.post("https://api.music.apple.com/v1/me/library/playlists").mock(
        return_value=httpx.Response(401)  # 未授權
    )

    with pytest.raises(httpx.HTTPStatusError):
        await push_to_apple_music([_MATCHED], "播放清單", DEV_TOKEN, USER_TOKEN)
