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

### 方式一：互動選單選擇來源

```bash
uv run kkbox2applemusic chart
```

不帶參數時顯示選單，選擇後自動比對並輸出至 `output/`。

### 方式二：指定來源代碼（適合自動化）

| 代碼 | 來源 |
|------|------|
| `daily` | 華語單曲日榜 |
| `daily-new` | 華語新歌日榜 |
| `weekly` | 華語單曲週榜 |
| `weekly-new` | 華語新歌週榜 |
| `yearly` | 華語年度單曲累積榜 |
| `qiankui` | 錢櫃國語點播榜 |

```bash
uv run kkbox2applemusic chart weekly --push
uv run kkbox2applemusic chart qiankui --push
```

### 方式三：從 `.kbl` 播放清單檔案推送

```bash
uv run kkbox2applemusic convert 播放清單.kbl --push
```

---

## 設定 Apple Developer 憑證

執行 `--push` 需要 Apple Developer 帳號憑證。複製 `.env.example` 為 `.env` 並填入：

```ini
APPLE_KEY_FILE=AuthKey_XXXXXXXXXX.p8   # .p8 私鑰檔路徑
APPLE_KEY_ID=XXXXXXXXXX                # Key ID（10 碼）
APPLE_TEAM_ID=XXXXXXXXXX               # Team ID（10 碼）
```

> `.p8` 私鑰與 Key ID、Team ID 可在 [Apple Developer 後台](https://developer.apple.com/account/resources/authkeys/list) 下載與查詢。

執行 `chart --push` 或 `convert --push` 時，若尚未取得 User Token，會自動開啟瀏覽器進行 Apple Music 帳號授權。

---

## 如何從 KKBOX 匯出 `.kbl`

1. 開啟 KKBOX 桌面版
2. 在播放清單上按右鍵 → 「匯出播放清單」
3. 選擇 `.kbl` 格式儲存

---

## 定時自動執行

設定後可讓排行榜更新時自動推送至 Apple Music，無需人工介入。

### 第一步：取得 Apple Music User Token（一次性）

```bash
uv run kkbox2applemusic auth
```

授權完成後將印出的 `APPLE_USER_TOKEN=eyJ...` 加入 `.env`：

```bash
echo 'APPLE_USER_TOKEN=eyJ...' >> .env
```

之後執行 `chart --push` 將直接使用此 token，不再跳出瀏覽器視窗。

### 第二步：設定 macOS LaunchAgent

`launchagent/` 目錄提供兩份範本：

| 檔案 | 排程 |
|------|------|
| `com.kkbox2applemusic.daily.plist` | 每天 08:30（日榜） |
| `com.kkbox2applemusic.weekly.plist` | 每週一 09:00（週榜） |

```bash
# 複製至 LaunchAgents 並啟用
cp launchagent/com.kkbox2applemusic.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kkbox2applemusic.daily.plist

# 查看執行 log
tail -f ~/Library/Logs/kkbox2applemusic.log
```

plist 預設使用 `--conflict replace`（每次更新同名清單），可依需求改為 `append` 或 `new`。

---

## Cache 機制

比對結果快取在 `output/<清單名稱>.csv`。1 小時內重複執行時直接從 cache 推送，跳過 API 比對：

```
第一次（或 cache 過期）：  scrape → 比對 API（慢）→ 寫 CSV → push
1 小時內再次執行：         scrape → 讀 CSV cache → push（跳過比對）
```

---

## 開發

```bash
uv run pytest         # 執行所有測試
uv run pytest tests/test_scraper.py -v
```

---

## 完整指令說明

### `auth` — 取得 User Token

```
uv run kkbox2applemusic auth [選項]
```

透過瀏覽器完成 Apple Music 帳號授權，印出 `APPLE_USER_TOKEN` 供寫入 `.env`。

### `chart` — 從 KKBOX 抓取並推送

```
uv run kkbox2applemusic chart [來源] [選項]
```

`來源` 可為代碼（見上方表格）或完整 URL；省略時顯示互動選單。

### `convert` — 從 `.kbl` 檔案推送

```
uv run kkbox2applemusic convert 播放清單.kbl [選項]
```

### 共用選項

| 選項 | 簡寫 | 預設值 | 說明 |
|------|------|--------|------|
| `--push` | | `False` | 直接推送至 Apple Music 帳號 |
| `--date-suffix` | | `False` | 清單名稱加上今天日期（如 `-20260430`） |
| `--conflict` | | `new` | 同名清單衝突處理（見下方） |
| `--output-dir` | `-o` | `output/` | 輸出目錄（同時作為 cache 目錄） |
| `--country` | `-c` | `tw` | iTunes Store 地區代碼 |
| `--key-file` | `-k` | | Apple Developer `.p8` 私鑰路徑（或 `APPLE_KEY_FILE`）|
| `--key-id` | | | Key ID（或 `APPLE_KEY_ID`）|
| `--team-id` | | | Team ID（或 `APPLE_TEAM_ID`）|
| `--user-token` | | | Music User Token，跳過授權（或 `APPLE_USER_TOKEN`）|
| `--dev-token` | | | Developer Token（或 `APPLE_DEV_TOKEN`）|

### `--conflict` 同名清單衝突處理

| 值 | 找到同名清單 | 找不到同名清單 |
|----|------------|--------------|
| `new`（預設）| 再建一個新的 | 建新清單 |
| `replace` | 刪除舊的，重新建立 | 建新清單 |
| `append` | 直接加入現有清單 | 建新清單 |

---

## 指令範例

```bash
# ── 互動選單 ──────────────────────────────────────────────
uv run kkbox2applemusic chart

# ── 排行榜（代碼） ────────────────────────────────────────
uv run kkbox2applemusic chart daily          # 華語單曲日榜
uv run kkbox2applemusic chart daily-new      # 華語新歌日榜
uv run kkbox2applemusic chart weekly         # 華語單曲週榜
uv run kkbox2applemusic chart weekly-new     # 華語新歌週榜
uv run kkbox2applemusic chart yearly         # 華語年度單曲累積榜
uv run kkbox2applemusic chart qiankui        # 錢櫃國語點播榜

# ── 完整 URL（任意來源） ──────────────────────────────────
uv run kkbox2applemusic chart "https://kma.kkbox.com/charts/daily/song?lang=tc&terr=tw"
uv run kkbox2applemusic chart "https://www.kkbox.com/tw/tc/playlist/__u6jEV61Qgdt4Tci1"

# ── 推送至 Apple Music ────────────────────────────────────
uv run kkbox2applemusic chart weekly --push
uv run kkbox2applemusic chart qiankui --push

# ── 衝突處理 ──────────────────────────────────────────────
uv run kkbox2applemusic chart daily --push --conflict replace   # 取代舊清單
uv run kkbox2applemusic chart daily --push --conflict append    # 累積至同一份清單
uv run kkbox2applemusic chart daily --push --date-suffix        # 清單名稱加今日日期

# ── 從 .kbl 檔案 ──────────────────────────────────────────
uv run kkbox2applemusic convert 播放清單.kbl
uv run kkbox2applemusic convert 播放清單.kbl --push
uv run kkbox2applemusic convert 播放清單.kbl --push --conflict replace
```
