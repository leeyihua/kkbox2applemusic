# kkbox2applemusic

將 KKBOX 播放清單（`.kbl`）轉換並直接推送至 Apple Music 帳號的命令列工具。

## 安裝

需要 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <repo>
cd kkbox2applemusic
uv sync
```

## 快速開始

### 方式一：直接推送至 Apple Music（建議）

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
uv run kkbox2applemusic 播放清單.kbl --push
```

執行後會自動開啟瀏覽器進行 Apple Music 帳號授權（登入 Apple ID），授權完成後程式自動繼續，播放清單會直接出現在你所有裝置的 Apple Music。

---

### 方式二：僅匯出檔案（無需憑證）

```bash
uv run kkbox2applemusic 播放清單.kbl
```

在 `output/` 目錄產生以下檔案，再手動匯入：

| 檔案 | 說明 |
|------|------|
| `播放清單.applescript` | 在 Script Editor 執行，搜尋並加入歌曲 |
| `播放清單.xml` | iTunes Library XML 格式 |
| `播放清單.txt` | Apple Music 相容 Tab 分隔文字 |
| `播放清單.csv` | 所有比對結果（含信心分數），供參考 |
| `unmatched.log` | 未比對到的歌曲（若全部成功則不產生） |

## 所有選項

```
uv run kkbox2applemusic [選項] 播放清單.kbl
```

| 選項 | 簡寫 | 預設值 | 說明 |
|------|------|--------|------|
| `--push` | | `False` | 直接推送至 Apple Music 帳號 |
| `--output-dir` | `-o` | `output/` | 輸出目錄 |
| `--country` | `-c` | `tw` | iTunes Store 地區代碼 |
| `--key-file` | `-k` | | Apple Developer `.p8` 私鑰路徑（或 `APPLE_KEY_FILE` 環境變數）|
| `--key-id` | | | Key ID（或 `APPLE_KEY_ID` 環境變數）|
| `--team-id` | | | Team ID（或 `APPLE_TEAM_ID` 環境變數）|
| `--user-token` | | | 直接傳入 Music User Token，跳過瀏覽器授權（或 `APPLE_USER_TOKEN` 環境變數）|
| `--dev-token` | | | 直接傳入 Developer Token（或 `APPLE_DEV_TOKEN` 環境變數）|

## 如何從 KKBOX 匯出 `.kbl`

1. 開啟 KKBOX 桌面版
2. 在播放清單上按右鍵 → 「匯出播放清單」
3. 選擇 `.kbl` 格式儲存

## 開發

```bash
# 執行所有測試
uv run pytest

# 執行單一測試檔
uv run pytest tests/test_pusher.py -v
```
