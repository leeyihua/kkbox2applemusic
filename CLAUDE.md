# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案目的

從 KKBOX 排行榜、KKBOX 公開播放清單或匯出的播放清單（`.kbl` 格式）取得歌曲，比對至 Apple Music 目錄後，輸出為可匯入的檔案，或直接推送至使用者的 Apple Music 帳號。

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
# 從 KKBOX 排行榜／播放清單抓取
uv run kkbox2applemusic chart                     # 不帶來源：顯示互動選單
uv run kkbox2applemusic chart daily --push        # 華語單曲日榜（昨天）
uv run kkbox2applemusic chart weekly --push       # 華語單曲週榜
uv run kkbox2applemusic chart qiankui --push      # 錢櫃國語點播榜（KKBOX playlist）
uv run kkbox2applemusic chart "https://..." --push  # 完整 URL（排行榜或 playlist 頁面）

# 從 .kbl 檔案轉換
uv run kkbox2applemusic convert <檔案.kbl> [--push]

# 取得 Apple Music User Token（一次性，結果寫入 .env 的 APPLE_USER_TOKEN）
uv run kkbox2applemusic auth

# 常用選項（chart / convert 共用）
#   --conflict new|replace|append   同名清單處理方式（預設 new）
#   --date-suffix                   清單名稱加上今天日期，例如「清單-20260430」
#   --output-dir/-o                 輸出目錄（預設 output/）
#   --country/-c                    商店地區代碼（預設 tw）

# 執行所有測試
uv run pytest

# 執行單一測試檔
uv run pytest tests/test_parser.py -v
```

## 環境變數（`.env`，範本見 `.env.example`）

| 變數 | 對應選項 | 說明 |
|------|---------|------|
| `APPLE_KEY_FILE` | `--key-file` | `.p8` 私鑰檔路徑 |
| `APPLE_KEY_ID` | `--key-id` | Key ID（10 碼） |
| `APPLE_TEAM_ID` | `--team-id` | Team ID（10 碼） |
| `APPLE_DEV_TOKEN` | `--dev-token` | 直接傳入開發者 JWT（優先於 .p8） |
| `APPLE_USER_TOKEN` | `--user-token` | Music User Token；未提供時 `--push` 會開瀏覽器授權 |

## 程式架構

```
src/kkbox2applemusic/
├── __init__.py    # 入口點，呼叫 cli.app
├── cli.py         # typer CLI，子指令：convert、chart、auth；含 CSV cache 與來源選單
├── parser.py      # 解析 .kbl → list[Song]
├── scraper.py     # 從 KKBOX 排行榜 API 或 playlist 頁面 HTML 抓取 → list[Song]
├── auth.py        # 產生開發者 JWT（ES256）；透過 MusicKit JS 取得 Music User Token
├── matcher.py     # 歌曲比對：有開發者 token 用 Apple Music API，否則用 iTunes Search API
├── exporter.py    # 輸出 TXT（主要）+ CSV + unmatched.log；load_from_csv() 供 cache 讀回
└── pusher.py      # 透過 Apple Music API 建立播放清單並加入歌曲
```

**資料流（.kbl）**：`.kbl` → `parse_kbl()` → `match_all()` → `export_*()` / `push_to_apple_music()`

**資料流（排行榜／playlist）**：KKBOX URL → `fetch_chart_songs()` 或 `fetch_playlist_songs()` → `match_all()` → `export_*()` / `push_to_apple_music()`

## 歌曲比對（matcher.py）

- `match_all()` 是 async，每首歌之間有 0.5 秒 rate limit 延遲
- 比對信心分數 < 0.42（`_MIN_CONFIDENCE`）視為未匹配；分數由歌名（65%）+ 歌手名（35%）相似度加權
- 結果含 Remix / Instrumental / Karaoke 等非原版關鍵字、但原歌名沒有時，分數 × 0.7
- 搜尋策略依序為：清理後歌名 + 各歌手變體 → 原始歌名 + 各歌手變體 → 純歌名；Various Artists／群星另加「歌名 + 專輯關鍵字」。分數 ≥ 0.8 即提前結束
- `_strip_song_name()` 移除影視／版本標注（主題曲、片尾曲、Live、Version 等），保留 feat. 與數字
- `_artist_variants()` 拆出「中文 (English)」、中英混寫、多位藝人等變體
- 有傳入 `dev_token` 時使用 `api.music.apple.com`，否則使用 `itunes.apple.com/search`；Apple Music API 回傳的是 catalog 標準名稱，可大幅提高 Music.app 的識別率

## KKBOX 來源（scraper.py / cli.py）

`cli.py` 的 `_SOURCES` 定義短代碼與互動選單順序：

| 代碼 | 名稱 | 類型 |
|------|------|------|
| `daily` | 華語單曲日榜 | 排行榜 |
| `daily-new` | 華語新歌日榜 | 排行榜 |
| `weekly` | 華語單曲週榜 | 排行榜 |
| `weekly-new` | 華語新歌週榜 | 排行榜 |
| `yearly` | 華語年度單曲累積榜 | 排行榜 |
| `qiankui` | 錢櫃國語點播榜 | KKBOX playlist |

- URL 符合 `_PLAYLIST_URL_RE`（`kkbox.com/.../playlist/`）時走 `fetch_playlist_songs()`，以 regex 解析頁面 HTML；否則走 `fetch_chart_songs()`
- 排行榜 API endpoint：`https://kma.kkbox.com/charts/api/v1/{period}`，不需要認證；period 與分類（`type`）從 URL 路徑解析
- 日榜需帶 `date`（昨天）參數，當日資料尚未就緒
- weekly 不帶 date 參數，API 自動回傳最新一週（帶 date 反而可能無資料）
- 各類型榜單上限：daily=50、weekly=50、yearly=100

## 認證（auth.py）

- `generate_developer_token()` 使用 PyJWT + cryptography 簽署 ES256 JWT，效期約 6 個月
- `get_music_user_token()` 在 `localhost:8765` 起臨時 HTTP server，開瀏覽器以 MusicKit JS 授權，120 秒逾時
- `--push` 必須有開發者 token；沒有 User Token 時會自動走瀏覽器授權。排程執行前應先用 `auth` 指令取得並寫入 `.env`

## Cache 機制

比對結果存於 `output/<清單名稱>.csv`。`_try_load_cache()` 檢查檔案修改時間，1 小時內（`_CACHE_TTL`）重複執行時直接以 `load_from_csv()` 讀回，跳過比對。

## 同名播放清單衝突處理（--conflict）

push 時可用 `--conflict` 指定同名清單的處理方式：

| 模式 | 找到同名清單 | 找不到同名清單 |
|------|------------|--------------|
| `new`（預設） | 再建一個新的 | 建新清單 |
| `replace` | 刪除舊的，重新建立 | 建新清單 |
| `append` | 直接加入現有清單 | 建新清單 |

實作位於 `pusher.py`：`_find_playlist_by_name()`（含分頁搜尋）、`_delete_playlist()`。`replace` 刪除時若回傳 401（MusicKit token 無 DELETE 權限），改為直接建新清單。加入歌曲以每批 100 首送出。

## 定時排程

`launchagent/` 提供 macOS LaunchAgent 範本：`daily.plist`（每天 08:30）、`weekly.plist`（每週一 09:00），預設 `--conflict replace`，log 寫至 `~/Library/Logs/kkbox2applemusic.log`。

## 注意事項

- `.txt` 匯出檔（如 `華語單曲日榜20260420-test2.txt`）存在中文編碼問題，應以 `.kbl` 為主要資料來源
- 程式輸出的 TXT 為 UTF-16 LE（含 BOM）、CRLF 換行、Tab 分隔，與 Apple Music「匯出播放列表」格式一致
- 歌名與專輯名稱中可能包含需要 XML escape 的字元（`<`、`>`、`&`），如 `&lt;`、`&amp;`
