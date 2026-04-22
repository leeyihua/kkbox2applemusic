"""測試 iTunes Library XML 與 AppleScript 輸出格式。"""

import plistlib
from pathlib import Path

from kkbox2applemusic.exporter import export_applescript, export_itunes_xml
from kkbox2applemusic.matcher import MatchResult
from kkbox2applemusic.parser import Song

_SONG = Song(name="晴天", artist="周杰倫 (Jay Chou)", album="葉惠美", kkbox_id="849514", track_id="abc")

_MATCHED = MatchResult(
    song=_SONG,
    matched=True,
    apple_track_id=12345678,
    apple_track_name="晴天",
    apple_artist="Jay Chou",
    apple_album="葉惠美",
    apple_url="https://music.apple.com/tw/album/q/1?i=12345678",
    confidence=0.95,
)

_UNMATCHED = MatchResult(song=_SONG, matched=False)


def test_export_itunes_xml_structure(tmp_path: Path):
    out = tmp_path / "test.xml"
    count = export_itunes_xml([_MATCHED], out, "測試播放清單")

    assert count == 1
    assert out.exists()

    with out.open("rb") as f:
        data = plistlib.load(f)

    assert data["Major Version"] == 1
    assert "Tracks" in data
    assert "Playlists" in data


def test_export_itunes_xml_track_fields(tmp_path: Path):
    out = tmp_path / "test.xml"
    export_itunes_xml([_MATCHED], out, "播放清單")

    with out.open("rb") as f:
        data = plistlib.load(f)

    track = next(iter(data["Tracks"].values()))
    assert track["Name"] == "晴天"
    assert track["Artist"] == "Jay Chou"
    assert track["Apple Music Item ID"] == 12345678
    assert isinstance(track["Apple Music Item ID"], int)   # 必須是整數，否則 Music.app 無法識別
    assert track["Kind"] == "Apple Music AAC audio file"
    assert track["Track Type"] == "Remote"                 # 告知 Music.app 這是串流曲目
    assert track["Apple Music Persistent ID"] == "BC614E"  # hex(12345678).upper()
    assert "Location" not in track  # 串流曲目不應有本地路徑


def test_export_itunes_xml_playlist(tmp_path: Path):
    out = tmp_path / "test.xml"
    export_itunes_xml([_MATCHED], out, "我的播放清單")

    with out.open("rb") as f:
        data = plistlib.load(f)

    playlist = data["Playlists"][0]
    assert playlist["Name"] == "我的播放清單"
    assert len(playlist["Playlist Items"]) == 1


def test_export_itunes_xml_skips_unmatched(tmp_path: Path):
    out = tmp_path / "test.xml"
    count = export_itunes_xml([_MATCHED, _UNMATCHED], out, "播放清單")

    assert count == 1

    with out.open("rb") as f:
        data = plistlib.load(f)

    assert len(data["Tracks"]) == 1


def test_export_itunes_xml_empty_returns_zero(tmp_path: Path):
    out = tmp_path / "test.xml"
    count = export_itunes_xml([_UNMATCHED], out, "播放清單")

    assert count == 0
    assert not out.exists()


# ── export_applescript ────────────────────────────────────────────────────────

def test_export_applescript_creates_file(tmp_path: Path):
    out = tmp_path / "test.applescript"
    count = export_applescript([_MATCHED], out, "測試播放清單")

    assert count == 1
    assert out.exists()


def test_export_applescript_contains_playlist_name(tmp_path: Path):
    out = tmp_path / "test.applescript"
    export_applescript([_MATCHED], out, "我的播放清單")

    content = out.read_text(encoding="utf-8")
    assert "我的播放清單" in content
    assert 'search (library playlist 1)' in content
    assert "add {item 1 of searchResults} to targetPlaylist" in content


def test_export_applescript_song_count(tmp_path: Path):
    out = tmp_path / "test.applescript"
    count = export_applescript([_MATCHED, _MATCHED, _UNMATCHED], out, "播放清單")

    assert count == 2  # 只算匹配的


def test_export_applescript_empty_returns_zero(tmp_path: Path):
    out = tmp_path / "test.applescript"
    count = export_applescript([_UNMATCHED], out, "播放清單")

    assert count == 0
    assert not out.exists()


def test_export_applescript_escapes_quotes(tmp_path: Path):
    """歌名含雙引號時應正確跳脫。"""
    song_with_quote = Song(name='Don"t Stop', artist="A", album="B", kkbox_id="1", track_id="x")
    result = MatchResult(
        song=song_with_quote, matched=True,
        apple_track_id=99, apple_track_name='Don"t Stop',
        apple_artist="A", apple_album="B", confidence=0.9,
    )
    out = tmp_path / "test.applescript"
    export_applescript([result], out, "播放清單")

    content = out.read_text(encoding="utf-8")
    # 不應有未跳脫的裸雙引號在搜尋字串中間
    assert 'search playlist "Apple Music" for "Don"t' not in content
