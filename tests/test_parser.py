"""測試 .kbl 解析器。"""

from pathlib import Path

from kkbox2applemusic.parser import Song, parse_kbl

FIXTURE = Path(__file__).parent / "fixtures" / "sample.kbl"


def test_parse_playlist_name():
    name, _ = parse_kbl(FIXTURE)
    assert name == "測試播放清單"


def test_parse_song_count():
    _, songs = parse_kbl(FIXTURE)
    assert len(songs) == 3


def test_parse_first_song():
    _, songs = parse_kbl(FIXTURE)
    song = songs[0]
    assert isinstance(song, Song)
    assert song.name == "晴天"
    assert song.artist == "周杰倫 (Jay Chou)"
    assert song.album == "葉惠美"
    assert song.kkbox_id == "849514"
    assert song.track_id == "PYki-YuSNHxJvvfWBT"


def test_parse_xml_escaped_name():
    """含有 XML escape 字元（&lt; &gt;）的歌名應正確解析。"""
    _, songs = parse_kbl(FIXTURE)
    song = songs[2]
    assert "<Passengers>" in song.name
    assert "&lt;" not in song.name
