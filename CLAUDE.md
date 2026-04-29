# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案目的

將 KKBOX 播放清單（`.kbl` 格式）轉換為可匯入 Apple Music 的格式。

## 輸入格式：KKBOX `.kbl` 檔案

`.kbl` 是 KKBOX 匯出的 XML 格式，根節點為 `<utf-8_data>`，結構如下：

```xml
<utf-8_data>
  <kkbox_package>
    <kkbox_ver>...</kkbox_ver>
    <playlist>
      <playlist_name>...</playlist_name>
      <playlist_data>
        <song_data>
          <song_name>歌曲名稱</song_name>
          <song_artist>演出者</song_artist>
          <song_album>專輯名稱</song_album>
          <song_pathname>KKBOX內部ID</song_pathname>
          <track_id>KKBOX Track ID</track_id>
          <song_song_idx>曲目編號</song_song_idx>
          <song_lyricsexist>1</song_lyricsexist>
          <song_playcnt>0</song_playcnt>
        </song_data>
        ...
      </playlist_data>
    </playlist>
    <package>
      <songcnt>100</songcnt>
    </package>
  </kkbox_package>
</utf-8_data>
```

## 常用指令

```bash
# 從 KKBOX 排行榜抓取並推送至 Apple Music
uv run kkbox2applemusic chart --push          # 華語年度新歌累積榜（預設）
uv run kkbox2applemusic chart daily --push    # 華語單曲日榜（昨天）
uv run kkbox2applemusic chart weekly --push   # 華語單曲週榜

# 從 .kbl 檔案轉換
uv run kkbox2applemusic convert <檔案.kbl>

# 使用 Apple Music API（搜尋結果更精確，需 Apple Developer 帳號）
uv run kkbox2applemusic convert <檔案.kbl> \
  --key-file AuthKey_XXXXXXXXXX.p8 \
  --key-id XXXXXXXXXX \
  --team-id XXXXXXXXXX

# 執行所有測試
uv run pytest

# 執行單一測試檔
uv run pytest tests/test_parser.py -v
```

## 程式架構

```
src/kkbox2applemusic/
├── __init__.py    # 入口點，呼叫 cli.app
├── cli.py         # typer CLI，整合兩個子指令：convert 與 chart
├── parser.py      # 解析 .kbl → list[Song]
├── scraper.py     # 從 KKBOX 排行榜網頁抓取 → list[Song]
├── auth.py        # 產生 Apple Music 開發者 JWT Token（ES256）
├── matcher.py     # 歌曲比對：優先用 Apple Music API，回退至 iTunes Search API
└── exporter.py    # 輸出 TXT（主要）+ CSV + unmatched.log
```

**資料流（.kbl）**：`.kbl` → `parse_kbl()` → `match_all()` → `export_*()` / `push_to_apple_music()`

**資料流（排行榜）**：KKBOX 排行榜 URL → `fetch_chart_songs()` → `match_all()` → `export_*()` / `push_to_apple_music()`

- `matcher.py` 的 `match_all()` 是 async，每首歌之間有 0.5 秒 rate limit 延遲
- 比對信心分數 < 0.38 視為未匹配；分數由歌名（65%）+ 歌手名（35%）相似度加權
- 有傳入 `dev_token` 時使用 `api.music.apple.com`，否則使用 `itunes.apple.com/search`
- Apple Music API 回傳的名稱為 catalog 標準名稱，可大幅提高 Music.app 的識別率
- `auth.py` 的 `generate_developer_token()` 使用 PyJWT + cryptography 簽署 ES256 JWT

## KKBOX 排行榜爬蟲說明（scraper.py）

- API endpoint：`https://kma.kkbox.com/charts/api/v1/{period}`，不需要認證
- 日榜需帶 `date`（昨天）參數，當日資料尚未就緒
- 各類型榜單上限：daily=50、weekly=100、yearly=100
- 短關鍵字對應：`daily` → 華語單曲日榜、`weekly` → 華語單曲週榜、`yearly` → 華語年度新歌累積榜

## 同名播放清單衝突處理（--conflict）

push 時可用 `--conflict` 指定同名清單的處理方式：

| 模式 | 找到同名清單 | 找不到同名清單 |
|------|------------|--------------|
| `new`（預設） | 再建一個新的 | 建新清單 |
| `replace` | 刪除舊的，重新建立 | 建新清單 |
| `append` | 直接加入現有清單 | 建新清單 |

實作位於 `pusher.py`：`_find_playlist_by_name()`（含分頁搜尋）、`_delete_playlist()`

## 注意事項

- `.txt` 匯出檔（如 `華語單曲日榜20260420-test2.txt`）存在中文編碼問題，應以 `.kbl` 為主要資料來源
- 歌名與專輯名稱中可能包含需要 XML escape 的字元（`<`、`>`、`&`），如 `&lt;`、`&amp;`
