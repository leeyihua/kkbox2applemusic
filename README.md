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

## 定時自動執行

設定完成後，每天/每週排行榜更新時可自動推送至 Apple Music，無需人工介入。

### 第一步：取得 Apple Music User Token（一次性）

```bash
uv run kkbox2applemusic auth
```

瀏覽器授權完成後，終端機會印出：

```
APPLE_USER_TOKEN=eyJ...
```

將這行加入 `.env` 即可：

```bash
echo 'APPLE_USER_TOKEN=eyJ...' >> .env
```

之後執行 `chart --push` 將直接使用此 token，不再跳出瀏覽器授權視窗。

### 第二步：設定 macOS LaunchAgent

`launchagent/` 目錄提供兩份範本：

| 檔案 | 排程 |
|------|------|
| `com.kkbox2applemusic.daily.plist` | 每天 08:30（日榜） |
| `com.kkbox2applemusic.weekly.plist` | 每週一 09:00（週榜） |

以日榜為例：

```bash
# 複製至 LaunchAgents 並啟用
cp launchagent/com.kkbox2applemusic.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kkbox2applemusic.daily.plist

# 查看執行 log
tail -f ~/Library/Logs/kkbox2applemusic.log
```

plist 預設使用 `--conflict replace`（每次更新同名清單），可依需求改為 `append` 或 `new`。

## Cache 機制

比對結果會快取在 `output/<清單名稱>.csv`。1 小時內重複執行同一份清單時，會跳過 API 比對步驟，直接從 cache 推送，大幅縮短執行時間。

```
第一次（或 cache 過期）：  scrape → 比對 API（慢）→ 寫 CSV → push
1 小時內再次執行：         scrape → 讀 CSV cache → push（跳過比對）
```

cache 有效期預設 1 小時，定義於 `cli.py` 的 `_CACHE_TTL = 3600`。

## 開發

```bash
# 執行所有測試
uv run pytest

# 執行單一測試檔
uv run pytest tests/test_scraper.py -v
```

---

## 指令完整說明

### `auth` — 取得 User Token

```
uv run kkbox2applemusic auth [選項]
```

透過瀏覽器完成 Apple Music 帳號授權，印出 `APPLE_USER_TOKEN` 供寫入 `.env`。
設定後所有指令皆可免互動授權，適合搭配定時排程使用。

### `chart` — 從 KKBOX 排行榜推送

```
uv run kkbox2applemusic chart [yearly|weekly|daily|URL] [選項]
```

### `convert` — 從 `.kbl` 檔案推送

```
uv run kkbox2applemusic convert 播放清單.kbl [選項]
```

### 共用選項

| 選項 | 簡寫 | 預設值 | 說明 |
|------|------|--------|------|
| `--push` | | `False` | 直接推送至 Apple Music 帳號 |
| `--date-suffix` | | `False` | 推送的清單名稱加上今天日期（如 `-20260430`） |
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

### `--date-suffix` 日期後綴

加上此旗標後，推送至 Apple Music 的播放清單名稱會附加今天的日期。
輸出檔案（TXT/CSV）與 cache 仍使用原始名稱，不受影響。

### 常用組合範例

```bash
# 每次建立新的同名清單（預設，會累積多份）
uv run kkbox2applemusic chart daily --push

# 每次建立帶日期的清單，例如「華語單曲日榜-20260430」
uv run kkbox2applemusic chart daily --push --date-suffix

# 每週更新同一份清單（取代舊的）
uv run kkbox2applemusic chart weekly --push --conflict replace

# 每天累積到同一份日榜清單
uv run kkbox2applemusic chart daily --push --conflict append
```
