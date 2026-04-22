"""輸出比對結果為 CSV、iTunes Library XML 與未匹配 log。"""

from __future__ import annotations

import csv
import plistlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .matcher import MatchResult

CSV_FIELDS = [
    "kkbox_name",
    "kkbox_artist",
    "kkbox_album",
    "kkbox_id",
    "matched",
    "confidence",
    "apple_track_id",
    "apple_track_name",
    "apple_artist",
    "apple_album",
    "apple_url",
]


def export_csv(results: list[MatchResult], output_path: Path) -> None:
    """將所有比對結果（含未匹配）輸出為 CSV。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "kkbox_name": r.song.name,
                    "kkbox_artist": r.song.artist,
                    "kkbox_album": r.song.album,
                    "kkbox_id": r.song.kkbox_id,
                    "matched": "Y" if r.matched else "N",
                    "confidence": f"{r.confidence:.2f}",
                    "apple_track_id": r.apple_track_id or "",
                    "apple_track_name": r.apple_track_name or "",
                    "apple_artist": r.apple_artist or "",
                    "apple_album": r.apple_album or "",
                    "apple_url": r.apple_url or "",
                }
            )


def export_txt(
    results: list[MatchResult],
    output_path: Path,
) -> int:
    """輸出為 Apple Music 相容的 UTF-16 LE Tab 分隔文字格式（.txt）。

    格式與 Apple Music「匯出播放列表」→ Unicode 文字相同：
    標題列 名稱\\t藝人\\t專輯，後接各曲資料列。

    回傳匯出的歌曲數量。
    """
    matched = [r for r in results if r.matched]
    if not matched:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["名稱\t藝人\t專輯"]
    for r in matched:
        name = r.apple_track_name or r.song.name
        artist = r.apple_artist or r.song.artist
        album = r.apple_album or r.song.album
        lines.append(f"{name}\t{artist}\t{album}")

    # UTF-16 LE with BOM，CRLF 換行（與 Apple Music 匯出格式一致）
    content = "\r\n".join(lines) + "\r\n"
    output_path.write_bytes(content.encode("utf-16-le"))
    # 手動加 BOM（UTF-16 LE BOM = FF FE）
    output_path.write_bytes(b"\xff\xfe" + content.encode("utf-16-le"))

    return len(matched)


def export_itunes_xml(
    results: list[MatchResult],
    output_path: Path,
    playlist_name: str,
) -> int:
    """將比對成功的歌曲輸出為 iTunes Library XML 格式。

    產生的 .xml 可透過 Music.app「檔案 > 資料庫 > 輸入播放列表」匯入。
    使用 Apple Music Item ID（iTunes Search API 的 trackId）讓 Music.app
    比對 Apple Music 串流目錄中的歌曲。

    回傳匯出的歌曲數量。
    """
    matched = [r for r in results if r.matched and r.apple_track_id]
    if not matched:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 建立 Tracks dict（key 為字串形式的本地 track ID）
    tracks: dict[str, object] = {}
    playlist_items: list[dict] = []

    for local_id, result in enumerate(matched, start=1):
        catalog_id = int(result.apple_track_id)  # type: ignore[arg-type]
        track_dict: dict[str, object] = {
            "Track ID": local_id,
            "Name": result.apple_track_name or result.song.name,
            "Artist": result.apple_artist or result.song.artist,
            "Album": result.apple_album or result.song.album,
            "Kind": "Apple Music AAC audio file",
            "Track Type": "Remote",
            "Apple Music Item ID": catalog_id,
            "Apple Music Persistent ID": format(catalog_id, "X").upper(),
        }
        tracks[str(local_id)] = track_dict
        playlist_items.append({"Track ID": local_id})

    library: dict[str, object] = {
        "Major Version": 1,
        "Minor Version": 1,
        "Application Version": "12.0",
        "Date": datetime.now(timezone.utc),
        "Features": 5,
        "Show Content Ratings": True,
        "Library Persistent ID": uuid.uuid4().hex[:16].upper(),
        "Tracks": tracks,
        "Playlists": [
            {
                "Name": playlist_name,
                "Playlist ID": 1,
                "Playlist Persistent ID": uuid.uuid4().hex[:16].upper(),
                "All Items": True,
                "Playlist Items": playlist_items,
            }
        ],
    }

    with output_path.open("wb") as f:
        plistlib.dump(library, f, fmt=plistlib.FMT_XML)

    return len(matched)


def export_applescript(
    results: list[MatchResult],
    output_path: Path,
    playlist_name: str,
) -> int:
    """輸出 AppleScript，在 macOS Script Editor 執行後直接建立 Apple Music 播放清單。

    AppleScript 會搜尋 Apple Music catalog 並加入歌曲，不需要歌曲事先在媒體庫中。

    執行方式：
        1. 雙擊 .applescript 檔案（Script Editor 開啟）
        2. 按「執行」按鈕（或 Cmd+R）
        3. 等待完成（約每首歌 1–2 秒）

    回傳匯出的歌曲數量。
    """
    matched = [r for r in results if r.matched]
    if not matched:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    def esc(s: str) -> str:
        """跳脫 AppleScript 字串中的雙引號。"""
        # AppleScript 無 \" 語法，改用 quote 常數串接
        parts = s.replace("\\", "\\\\").split('"')
        return '" & quote & "'.join(parts)

    pl = esc(playlist_name)
    lines = [
        f"-- 自動產生的 Apple Music 播放清單匯入腳本",
        f"-- 播放清單：{playlist_name}（共 {len(matched)} 首）",
        f"-- 執行方式：在 Script Editor.app 中開啟，按「執行」（Cmd+R）",
        f"",
        f'tell application "Music"',
        f'\tif not (exists user playlist "{pl}") then',
        f'\t\tmake new user playlist with properties {{name:"{pl}"}}',
        f'\tend if',
        f'\tset targetPlaylist to user playlist "{pl}"',
        f"",
    ]

    for i, r in enumerate(matched, start=1):
        name = esc(r.apple_track_name or r.song.name)
        artist = esc(r.apple_artist or r.song.artist)
        comment = r.apple_track_name or r.song.name
        lines += [
            f"\t-- {i}/{len(matched)}: {comment}",
            f'\tset searchResults to search (library playlist 1) for "{name} {artist}" only music',
            f"\tif (count of searchResults) > 0 then",
            f"\t\tadd {{item 1 of searchResults}} to targetPlaylist",
            f"\tend if",
            f"",
        ]

    lines.append("end tell")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(matched)


def export_unmatched_log(results: list[MatchResult], log_path: Path) -> None:
    """將未匹配的歌曲記錄到 log 檔。"""
    unmatched = [r for r in results if not r.matched]
    if not unmatched:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"未匹配歌曲清單（共 {len(unmatched)} 首）\n")
        f.write("=" * 50 + "\n")
        for r in unmatched:
            f.write(f"歌名：{r.song.name}\n")
            f.write(f"演出者：{r.song.artist}\n")
            f.write(f"專輯：{r.song.album}\n")
            f.write(f"信心分數：{r.confidence:.2f}\n")
            f.write("-" * 30 + "\n")
