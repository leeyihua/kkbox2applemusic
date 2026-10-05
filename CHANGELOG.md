# 更新紀錄

本專案版本紀錄依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 格式撰寫。

---

## [Unreleased] — 2026-10-05

### 修改
- 歌曲比對改進（`matcher.py`）：
  - 非原版扣分關鍵字加入「粵語版」、「伴奏」，避免選中粵語版或伴奏版
  - 「歌名 - 副標」格式（如「甲乙丙丁 - 你我怎麼兩清」）補上以主標搜尋的查詢
  - KKBOX 以節目／原聲帶名稱當演出者時（如「天賜的聲音」），名稱出現在結果專輯中即視為藝人相符
  - 僅由純歌名查詢找到、且藝人明顯不符的同名歌曲，分數乘以 0.6，降低誤配
- `convert` 指令說明範例補上子指令名稱
- CLAUDE.md 更新為與程式碼一致（信心門檻 0.42、`pusher.py`、來源代碼、環境變數、cache、排程等）

### 新增
- `tests/test_cli.py`：37 個 CLI 測試（token 取得、cache、來源選單、匯出、推送、授權與錯誤處理）
- `tests/test_matcher.py`：8 個新比對規則的測試

### 已知限制
- 演出者不在 Apple Music 目錄、但有同名翻唱且歌手名部分字元相同時（如 RG-老帅 → 老闆）仍可能誤配，推送前請檢查 CSV 中的低分項目

---

## [0.2.1] — 2026-04-30

### 修改
- `pyproject.toml` 最低 Python 版本從 3.14 放寬至 3.11，提升跨平台相容性
- README 新增 Windows / Linux 安裝說明，以及各平台（macOS / Windows / Linux）的定時排程設定方式

---

## [0.2.0] — 2026-04-30

### 新增
- `chart` 指令新增互動選單：不帶來源參數時顯示編號選單供互動選擇
- 新增 6 個預定義來源代碼，支援直接指定（適合自動化）：
  - `daily` — 華語單曲日榜
  - `daily-new` — 華語新歌日榜
  - `weekly` — 華語單曲週榜
  - `weekly-new` — 華語新歌週榜
  - `yearly` — 華語年度單曲累積榜
  - `qiankui` — 錢櫃國語點播榜
- 支援 KKBOX playlist 頁面 URL（`www.kkbox.com/*/playlist/*`），透過 HTML 解析取得歌名、歌手、專輯，無需額外 API 認證

---

## [0.1.0] — 2026-04

### 新增
- 從 KKBOX 排行榜（日榜 / 週榜 / 年榜）抓取並推送至 Apple Music（`chart` 指令）
- 解析 KKBOX `.kbl` 播放清單並推送（`convert` 指令）
- Apple Music 開發者 Token 授權流程（`auth` 指令）
- iTunes Search API 比對（無需金鑰）與 Apple Music API 比對（需 Developer 帳號）
- 比對結果 Cache（1 小時 TTL），重複執行不重複呼叫比對 API
- 推送同名清單衝突處理（`--conflict new / replace / append`）
- 播放清單名稱日期後綴（`--date-suffix`）
- macOS LaunchAgent 排程範本（`launchagent/`）
