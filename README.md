# kkbox2applemusic

從 KKBOX 排行榜或播放清單（`.kbl`）抓取歌曲，並直接推送至 Apple Music 帳號的命令列工具。

## 安裝

需要 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <repo>
cd kkbox2applemusic
uv sync
```

## 快速開始

### 方式一：從 KKBOX 排行榜直接推送（最簡單）

```bash
uv run kkbox2applemusic chart --push          # 華語年度新歌累積榜（預設）
uv run kkbox2applemusic chart daily --push    # 華語單曲日榜
uv run kkbox2applemusic chart weekly --push   # 華語單曲週榜
```

不帶 `--push` 只會在 `output/` 產生 TXT/CSV 檔案而不推送。

也可以貼完整 KKBOX 排行榜 URL：

```bash
uv run kkbox2applemusic chart "https://kma.kkbox.com/charts/daily/song?lang=tc&terr=tw" --push
```

---

### 方式二：從 `.kbl` 播放清單檔案推送

需要 Apple Developer 帳號憑證，一次設定、永久使用。

**第一步：設定憑證**

複製 `.env.example` 為 `.env`，填入你的 Apple Developer 資訊：

```bash
cp .env.example .env
```

```ini
APPLE_KEY_FILE=AuthKey_XXXXXXXXXX.p8   # .p8 私鑰檔路徑
APPLE_KEY_ID=XXXXXXXXXX                # Key ID（10 碼）
APPLE_TEAM_ID=XXXXXXXXXX               # Team ID（10 碼）
```

> `.p8` 私鑰與 Key ID、Team ID 可在 [Apple Developer 後台](https://developer.apple.com/account/resources/authkeys/list) 下載與查詢。

**第二步：執行推送**

```bash
uv run kkbox2applemusic convert 播放清單.kbl --push
```

執行後會自動開啟瀏覽器進行 Apple Music 帳號授權（登入 Apple ID），授權完成後播放清單會直接出現在你所有裝置的 Apple Music。

---

### 方式三：僅匯出檔案（無需憑證）

```bash
uv run kkbox2applemusic convert 播放清單.kbl
```

在 `output/` 目錄產生以下檔案：

| 檔案 | 說明 |
|------|------|
| `播放清單.txt` | Apple Music 相容 Tab 分隔文字 |
| `播放清單.csv` | 所有比對結果（含信心分數），供參考 |
| `unmatched.log` | 未比對到的歌曲（若全部成功則不產生） |

## 如何從 KKBOX 匯出 `.kbl`

1. 開啟 KKBOX 桌面版
2. 在播放清單上按右鍵 → 「匯出播放清單」
3. 選擇 `.kbl` 格式儲存

## 所有選項

### `chart` 指令

```
uv run kkbox2applemusic chart [yearly|weekly|daily|URL] [選項]
```

| 選項 | 簡寫 | 預設值 | 說明 |
|------|------|--------|------|
| `--push` | | `False` | 直接推送至 Apple Music 帳號 |
| `--output-dir` | `-o` | `output/` | 輸出目錄 |
| `--country` | `-c` | `tw` | iTunes Store 地區代碼 |
| `--key-file` | `-k` | | Apple Developer `.p8` 私鑰路徑（或 `APPLE_KEY_FILE`）|
| `--key-id` | | | Key ID（或 `APPLE_KEY_ID`）|
| `--team-id` | | | Team ID（或 `APPLE_TEAM_ID`）|
| `--user-token` | | | Music User Token，跳過瀏覽器授權（或 `APPLE_USER_TOKEN`）|
| `--dev-token` | | | Developer Token（或 `APPLE_DEV_TOKEN`）|

### `convert` 指令

```
uv run kkbox2applemusic convert 播放清單.kbl [選項]
```

選項與 `chart` 相同。

## 開發

```bash
# 執行所有測試
uv run pytest

# 執行單一測試檔
uv run pytest tests/test_scraper.py -v
```
