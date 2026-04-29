"""測試 KKBOX 排行榜爬蟲。"""

import pytest
import respx
import httpx

from kkbox2applemusic.scraper import fetch_chart_songs, _CHART_API_BASE

SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
<title>華語年度單曲累積榜 - KKBOX 風雲榜</title>
</head>
<body></body>
</html>"""

SAMPLE_CHART_RESPONSE = {
    "code": "0",
    "message": "OK",
    "data": {
        "year": "2026",
        "charts": {
            "newrelease": [
                {
                    "song_name": "晴天",
                    "artist_roles": "周杰倫",
                    "album_name": "葉惠美",
                    "song_id": "abc123",
                    "type": "song",
                },
                {
                    "song_name": "稻香",
                    "artist_roles": "周杰倫",
                    "album_name": "魔杰座",
                    "song_id": "def456",
                    "type": "song",
                },
                {
                    "song_name": "不該",
                    "artist_roles": "周杰倫 / 張惠妹",
                    "album_name": "周杰倫的床邊故事",
                    "song_id": "ghi789",
                    "type": "song",
                },
                {
                    "song_name": "某精選",
                    "artist_roles": "Various Artists",
                    "album_name": "精選合輯",
                    "song_id": "jkl000",
                    "type": "album",  # 應被過濾掉
                },
            ]
        },
        "playlist_id": "HZskVUizzAH67S1--c",
    },
}

CHART_URL = "https://kma.kkbox.com/charts/yearly/newrelease?lang=tc&terr=tw"
API_URL = f"{_CHART_API_BASE}/yearly"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_chart_songs_success():
    """正常情境：取得歌曲清單並過濾掉 album 類型。"""
    respx.get(CHART_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=SAMPLE_CHART_RESPONSE))

    playlist_name, songs = await fetch_chart_songs(CHART_URL)

    assert playlist_name == "華語年度單曲累積榜"
    assert len(songs) == 3  # album 類型被過濾
    assert songs[0].name == "晴天"
    assert songs[0].artist == "周杰倫"
    assert songs[0].album == "葉惠美"
    assert songs[0].kkbox_id == "abc123"
    assert songs[0].track_id == ""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_chart_songs_multi_artist():
    """多藝人歌曲的 artist_roles 應原樣保留。"""
    respx.get(CHART_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=SAMPLE_CHART_RESPONSE))

    _, songs = await fetch_chart_songs(CHART_URL)

    multi = songs[2]
    assert multi.name == "不該"
    assert multi.artist == "周杰倫 / 張惠妹"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_chart_songs_limit_param():
    """API 請求應包含 limit=100 參數。"""
    respx.get(CHART_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))

    captured_url = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url
        captured_url = str(request.url)
        return httpx.Response(200, json=SAMPLE_CHART_RESPONSE)

    respx.get(API_URL).mock(side_effect=capture)

    await fetch_chart_songs(CHART_URL)

    assert "limit=100" in captured_url


@pytest.mark.asyncio
@respx.mock
async def test_fetch_chart_songs_empty_charts():
    """API 回傳空的 charts 時應拋出 RuntimeError。"""
    empty_response = {"code": "0", "data": {"charts": {}}}
    respx.get(CHART_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=empty_response))

    with pytest.raises(RuntimeError, match="找不到排行榜資料"):
        await fetch_chart_songs(CHART_URL)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_chart_songs_api_error():
    """KKBOX API 回傳錯誤時應拋出 httpx.HTTPStatusError。"""
    respx.get(CHART_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
    respx.get(API_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_chart_songs(CHART_URL)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_chart_songs_period_from_url():
    """從 URL 路徑解析排行榜類型（daily）並呼叫對應 API。"""
    daily_url = "https://kma.kkbox.com/charts/daily/newrelease?lang=tc&terr=tw"
    daily_api_url = f"{_CHART_API_BASE}/daily"

    respx.get(daily_url).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
    respx.get(daily_api_url).mock(return_value=httpx.Response(200, json=SAMPLE_CHART_RESPONSE))

    _, songs = await fetch_chart_songs(daily_url)
    assert len(songs) == 3
