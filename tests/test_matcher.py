"""測試 iTunes Search API 比對邏輯。"""

import pytest
import respx
import httpx

from kkbox2applemusic.matcher import (
    ITUNES_SEARCH_URL,
    _artist_variants,
    _extract_album_keyword,
    _score_candidate,
    _strip_song_name,
    match_song,
)
from kkbox2applemusic.parser import Song

SAMPLE_SONG = Song(
    name="晴天",
    artist="周杰倫 (Jay Chou)",
    album="葉惠美",
    kkbox_id="849514",
    track_id="PYki-YuSNHxJvvfWBT",
)

MOCK_RESPONSE = {
    "resultCount": 1,
    "results": [
        {
            "trackId": 123456,
            "trackName": "晴天",
            "artistName": "Jay Chou",
            "collectionName": "葉惠美",
            "trackViewUrl": "https://music.apple.com/tw/album/qing-tian/123456",
        }
    ],
}


# ── _strip_song_name ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, expected", [
    # 移除影視後綴（含 " - "）
    ("幸福在歌唱 - 電影《陽光女子合唱團》幸福版主題曲", "幸福在歌唱"),
    ("如果可以 - 電影\"月老\"主題曲", "如果可以"),
    ("任性 - 電視劇《難哄》主題曲", "任性"),
    ("頻率 - 影集《向流星許願的我們》片頭曲", "頻率"),
    ("運轉人生 - 影集《華麗計程車行》插曲", "運轉人生"),
    ("今天的我 - 電影《冠軍之路》主題曲", "今天的我"),
    ("布拉格廣場 - JOLIN Version/ 星宇航空布拉格開航主題曲", "布拉格廣場"),
    ("座位 - Live", "座位"),
    # 移除括號內的影視標注
    ("一念 (影视剧《逐玉》插曲)", "一念"),
    ("我對緣分小心翼翼 (劇集《逐玉》主題曲)", "我對緣分小心翼翼"),
    ("孤單心事-音樂產房(原唱:藍又時)(Live)", "孤單心事"),
    ("像晴天像雨天（電視劇《難哄》心動曲）", "像晴天像雨天"),
    ("必巡 (三立戲劇《含笑食堂》片尾曲／《嘉慶君遊臺灣》片頭曲)", "必巡"),
    # 劇名前綴 + 媒體關鍵字（劇名在關鍵字前面）
    ("雨愛 - 海派甜心片尾曲", "雨愛"),
    ("家家酒 - 三立華劇<極品絕配>片尾曲", "家家酒"),
    ("生存遊戲 feat. W0LF(S)五堅情 - 戲劇「舊金山美容院」片尾曲", "生存遊戲 feat. W0LF(S)五堅情"),
    # 中文 Live（现场）
    ("訣愛·盡 - 现场", "訣愛·盡"),
    # 推廣曲後綴
    ("月 - EMOTIF情緒推廣曲", "月"),
    # 保留 feat. 與歌名本身的副標
    ("聖誕星 (feat. 楊瑞代)", "聖誕星 (feat. 楊瑞代)"),
    ("左轉燈 (1000 Times+1)", "左轉燈 (1000 Times+1)"),
    ("Jumping Machine (跳樓機)", "Jumping Machine (跳樓機)"),
    # 無標注歌名不變
    ("晴天", "晴天"),
    ("告白氣球", "告白氣球"),
])
def test_strip_song_name(name, expected):
    assert _strip_song_name(name) == expected


# ── _artist_variants ──────────────────────────────────────────────────────────

def test_artist_variants_dual_language():
    variants = _artist_variants("周杰倫 (Jay Chou)")
    assert "Jay Chou" in variants
    assert "周杰倫" in variants

def test_artist_variants_gem():
    variants = _artist_variants("G.E.M. 鄧紫棋")
    assert "G.E.M." in variants or "鄧紫棋" in variants

def test_artist_variants_various():
    assert _artist_variants("Various Artists") == [""]

def test_artist_variants_plain():
    variants = _artist_variants("張遠")
    assert "張遠" in variants


# ── match_song ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_match_song_success():
    respx.get(ITUNES_SEARCH_URL).mock(return_value=httpx.Response(200, json=MOCK_RESPONSE))

    async with httpx.AsyncClient() as client:
        result = await match_song(SAMPLE_SONG, client)

    assert result.matched is True
    assert result.apple_track_id == 123456
    assert result.apple_track_name == "晴天"
    assert result.confidence > 0.4


@pytest.mark.asyncio
@respx.mock
async def test_match_song_with_subtitle_strips_and_finds():
    """含影視標注的歌名，應在 strip 後成功比對。"""
    song = Song(
        name="幸福在歌唱 - 電影《陽光女子合唱團》幸福版主題曲",
        artist="A-Lin",
        album="幸福在歌唱",
        kkbox_id="111",
        track_id="abc",
    )
    response = {
        "resultCount": 1,
        "results": [{"trackId": 999, "trackName": "幸福在歌唱", "artistName": "A-Lin",
                     "collectionName": "幸福在歌唱 - Single", "trackViewUrl": ""}],
    }
    respx.get(ITUNES_SEARCH_URL).mock(return_value=httpx.Response(200, json=response))

    async with httpx.AsyncClient() as client:
        result = await match_song(song, client)

    assert result.matched is True
    assert result.apple_track_name == "幸福在歌唱"


# ── _extract_album_keyword ────────────────────────────────────────────────────

@pytest.mark.parametrize("album, expected", [
    ("《逐玉》 影视原声带",  "逐玉"),
    ("逐玉原聲帶",           "逐玉"),
    ("葉惠美",               "葉惠美"),
    ("",                     ""),
    ("【難哄】OST",          "難哄"),
])
def test_extract_album_keyword(album, expected):
    assert _extract_album_keyword(album) == expected


# ── Various Artists 評分應使用專輯關鍵字 ────────────────────────────────────

def test_score_various_artists_prefers_ost_album():
    """Various Artists 歌曲：專輯關鍵字吻合的候選應得到比同名熱門歌曲更高的分數。"""
    wrong = {"trackName": "一念", "artistName": "三妹",   "collectionName": "一念 - Single"}
    right = {"trackName": "一念", "artistName": "張紫寧", "collectionName": "逐玉原聲帶"}

    wrong_score = _score_candidate("一念", "Various Artists", wrong, "《逐玉》 影视原声带")
    right_score = _score_candidate("一念", "Various Artists", right, "《逐玉》 影视原声带")

    assert right_score > wrong_score, (
        f"正確 OST 版本應得分更高：right={right_score:.3f} wrong={wrong_score:.3f}"
    )


@pytest.mark.asyncio
@respx.mock
async def test_match_song_various_artists_searches_by_name():
    """Various Artists 應以純歌名搜尋。"""
    song = Song(name="一念", artist="Various Artists", album="", kkbox_id="222", track_id="xyz")
    response = {
        "resultCount": 1,
        "results": [{"trackId": 888, "trackName": "一念", "artistName": "張紫寧",
                     "collectionName": "逐玉原聲帶", "trackViewUrl": ""}],
    }
    respx.get(ITUNES_SEARCH_URL).mock(return_value=httpx.Response(200, json=response))

    async with httpx.AsyncClient() as client:
        result = await match_song(song, client)

    assert result.matched is True


@pytest.mark.asyncio
@respx.mock
async def test_match_song_various_artists_with_album_prefers_ost():
    """Various Artists 且有專輯名稱時，OST 版本應優先於同名熱門歌曲。"""
    song = Song(
        name="一念 (影视剧《逐玉》插曲)",
        artist="Various Artists",
        album="《逐玉》 影视原声带",
        kkbox_id="1400711221",
        track_id="abc",
    )
    # API 回傳兩個候選：熱門同名歌曲 + 正確 OST 版本
    response = {
        "resultCount": 2,
        "results": [
            {"trackId": 1763029229, "trackName": "一念", "artistName": "三妹",
             "collectionName": "一念 - Single", "trackViewUrl": ""},
            {"trackId": 888000001,  "trackName": "一念", "artistName": "張紫寧",
             "collectionName": "逐玉原聲帶", "trackViewUrl": ""},
        ],
    }
    respx.get(ITUNES_SEARCH_URL).mock(return_value=httpx.Response(200, json=response))

    async with httpx.AsyncClient() as client:
        result = await match_song(song, client)

    assert result.matched is True
    assert result.apple_track_id == 888000001, (
        f"應選中 OST 版本（張紫寧），但選中了 {result.apple_artist}/{result.apple_album}"
    )


@pytest.mark.asyncio
@respx.mock
async def test_match_song_various_artists_feat_odd_chars_uses_core_name():
    """feat. 後含特殊字元時，應透過「核心歌名 + 專輯關鍵字」找到正確歌曲。

    "生存遊戲 feat. W0LF(S)五堅情 舊金山美容院" → iTunes 無結果（W0LF(S) 干擾）
    "生存遊戲 舊金山美容院"                      → 找到動力火車版
    """
    song = Song(
        name="生存遊戲 feat. W0LF(S)五堅情 - 戲劇「舊金山美容院」片尾曲",
        artist="Various Artists",
        album="戲劇「舊金山美容院」原聲帶",
        kkbox_id="x", track_id="y",
    )
    correct = {
        "trackId": 99999,
        "trackName": "生存遊戲 (feat. 五堅情 WOLF(S)) [戲劇「舊金山美容院」片尾曲]",
        "artistName": "動力火車",
        "collectionName": "戲劇「舊金山美容院」原聲帶 - EP",
        "trackViewUrl": "",
    }

    def _side_effect(request):
        term = request.url.params.get("term", "")
        # 只有去掉 feat. 後的簡化查詢才能找到正確歌曲
        if "舊金山美容院" in term and "W0LF" not in term:
            return httpx.Response(200, json={"resultCount": 1, "results": [correct]})
        return httpx.Response(200, json={"resultCount": 0, "results": []})

    respx.get(ITUNES_SEARCH_URL).mock(side_effect=_side_effect)

    async with httpx.AsyncClient() as client:
        result = await match_song(song, client)

    assert result.matched is True
    assert result.apple_track_id == 99999
    assert result.apple_artist == "動力火車"


@pytest.mark.asyncio
@respx.mock
async def test_match_song_no_results():
    respx.get(ITUNES_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"resultCount": 0, "results": []})
    )

    async with httpx.AsyncClient() as client:
        result = await match_song(SAMPLE_SONG, client)

    assert result.matched is False
    assert result.apple_track_id is None


@pytest.mark.asyncio
@respx.mock
async def test_match_song_low_confidence():
    """完全不相關的搜尋結果應視為未匹配。"""
    bad_response = {
        "resultCount": 1,
        "results": [{"trackId": 999, "trackName": "完全不同的歌", "artistName": "另一個歌手",
                     "collectionName": "某張專輯", "trackViewUrl": ""}],
    }
    respx.get(ITUNES_SEARCH_URL).mock(return_value=httpx.Response(200, json=bad_response))

    async with httpx.AsyncClient() as client:
        result = await match_song(SAMPLE_SONG, client)

    assert result.matched is False


@pytest.mark.asyncio
@respx.mock
async def test_match_song_http_error():
    respx.get(ITUNES_SEARCH_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        result = await match_song(SAMPLE_SONG, client)

    assert result.matched is False
