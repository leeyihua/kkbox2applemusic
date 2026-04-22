"""解析 KKBOX .kbl 播放清單檔案。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Song:
    name: str
    artist: str
    album: str
    kkbox_id: str    # song_pathname
    track_id: str    # KKBOX track_id


def parse_kbl(path: Path | str) -> tuple[str, list[Song]]:
    """解析 .kbl 檔案，回傳 (播放清單名稱, 歌曲清單)。

    .kbl 是 KKBOX 匯出的 XML 格式，根節點為 <utf-8_data>。
    """
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    playlist_name_el = root.find(".//playlist_name")
    playlist_name = playlist_name_el.text if playlist_name_el is not None else path.stem

    songs: list[Song] = []
    for song_el in root.findall(".//song_data"):

        def text(tag: str) -> str:
            el = song_el.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        songs.append(
            Song(
                name=text("song_name"),
                artist=text("song_artist"),
                album=text("song_album"),
                kkbox_id=text("song_pathname"),
                track_id=text("track_id"),
            )
        )

    return playlist_name, songs
