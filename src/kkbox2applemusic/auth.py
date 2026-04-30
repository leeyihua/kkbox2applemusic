"""產生 Apple Music API 開發者 JWT Token，以及取得 Music User Token。"""

from __future__ import annotations

import time
from pathlib import Path

import jwt


def generate_developer_token(
    key_file: Path | str,
    key_id: str,
    team_id: str,
    expiry_seconds: int = 15777000,  # ~6 個月（Apple 最長允許值）
) -> str:
    """從 .p8 私鑰檔案產生 Apple Music API 開發者 JWT Token。

    Args:
        key_file:        Apple Developer 下載的 .p8 私鑰檔路徑
        key_id:          對應的 Key ID（10 碼英數字串）
        team_id:         Apple Developer Team ID（10 碼）
        expiry_seconds:  Token 有效時間（秒）

    Returns:
        JWT token 字串，可直接用於 Authorization: Bearer <token> 標頭。

    Raises:
        FileNotFoundError: 找不到 .p8 檔案
        ValueError:        key_id 或 team_id 格式不符
    """
    key_path = Path(key_file)
    if not key_path.exists():
        raise FileNotFoundError(f"找不到私鑰檔案：{key_path}")
    if not key_id or len(key_id) != 10:
        raise ValueError(f"key_id 應為 10 碼英數字串，收到：{key_id!r}")
    if not team_id or len(team_id) != 10:
        raise ValueError(f"team_id 應為 10 碼英數字串，收到：{team_id!r}")

    private_key = key_path.read_text()
    now = int(time.time())

    headers = {"alg": "ES256", "kid": key_id}
    payload = {
        "iss": team_id,
        "iat": now,
        "exp": now + expiry_seconds,
    }

    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


# MusicKit JS 授權頁面（嵌入開發者 Token，於本機 localhost 執行）
_AUTH_HTML = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Apple Music 授權 — kkbox2applemusic</title>
  <script src="https://js-cdn.music.apple.com/musickit/v3/musickit.js" async></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
           max-width: 440px; margin: 80px auto; text-align: center;
           color: #1d1d1f; padding: 0 24px; }
    h1 { font-size: 22px; font-weight: 600; }
    p  { color: #6e6e73; line-height: 1.6; }
    .ok  { color: #34c759; font-weight: 600; }
    .err { color: #ff3b30; }
  </style>
</head>
<body>
  <h1>🎵 Apple Music 授權</h1>
  <p id="msg">正在載入 MusicKit，請稍候…</p>
  <script>
    document.addEventListener('musickitloaded', async () => {
      const msg = document.getElementById('msg');
      try {
        await MusicKit.configure({
          developerToken: '__DEVELOPER_TOKEN__',
          app: { name: 'kkbox2applemusic', build: '1.0.0' },
          permissions: 'music.library'
        });
        const music = MusicKit.getInstance();
        msg.textContent = '請在彈出視窗中以您的 Apple ID 登入…';
        await music.authorize({ forceAuthorization: true });
        const token = music.musicUserToken;
        if (!token) throw new Error('取得 Music User Token 失敗，請確認已訂閱 Apple Music');
        msg.textContent = '傳送授權資訊中…';
        await fetch('/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token })
        });
        msg.className = 'ok';
        msg.textContent = '✓ 授權成功！可以關閉此視窗，程式將自動繼續。';
      } catch (e) {
        msg.className = 'err';
        msg.textContent = '授權失敗：' + e.message;
      }
    });
  </script>
</body>
</html>
"""


def get_music_user_token(developer_token: str, port: int = 8765) -> str:
    """透過 MusicKit JS 瀏覽器授權流程取得 Music User Token。

    流程：
    1. 在 localhost:{port} 啟動臨時 HTTP server
    2. 開啟瀏覽器至 http://localhost:{port}/auth
    3. 使用者在瀏覽器完成 Apple ID 授權（MusicKit JS）
    4. 取得 token 後關閉 server，回傳 token

    Args:
        developer_token: 由 generate_developer_token() 產生的 JWT
        port:            本機監聽埠號（預設 8765）

    Returns:
        Music User Token 字串，用於 Music-User-Token 標頭。

    Raises:
        TimeoutError: 120 秒內未完成授權
    """
    import json
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    html = _AUTH_HTML.replace("__DEVELOPER_TOKEN__", developer_token)
    token_holder: dict[str, str] = {}
    done = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/auth":
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            if self.path == "/token":
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length))
                token_holder["token"] = data["token"]
                self.send_response(200)
                self.end_headers()
                done.set()

        def log_message(self, *args: object) -> None:  # 靜默 HTTP log
            pass

    server = HTTPServer(("localhost", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        webbrowser.open(f"http://localhost:{port}/auth")
        if not done.wait(timeout=120):
            raise TimeoutError("等待 Apple Music 授權逾時（2 分鐘），請重新執行。")
        return token_holder["token"]
    finally:
        server.shutdown()
