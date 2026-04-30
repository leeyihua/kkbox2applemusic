"""命令列介面。"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from pathlib import Path
from typing import Optional

_CACHE_TTL = 3600  # 秒，cache 有效期限（1 小時）

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from .exporter import export_csv, export_txt, export_unmatched_log
from .matcher import MatchResult, match_all
from .parser import Song, parse_kbl

load_dotenv()

app = typer.Typer(help="將 KKBOX 播放清單（.kbl）轉換為 Apple Music 格式")
console = Console()


def _get_dev_token(
    key_file: Optional[Path],
    key_id: Optional[str],
    team_id: Optional[str],
    dev_token: Optional[str],
) -> Optional[str]:
    """取得 Apple Music 開發者 Token（直接傳入或從 .p8 產生）。"""
    if dev_token:
        return dev_token
    if key_file and key_id and team_id:
        from .auth import generate_developer_token
        try:
            token = generate_developer_token(key_file, key_id, team_id)
            console.print("[dim]Apple Music API：使用開發者 Token[/dim]")
            return token
        except Exception as e:
            console.print(f"[yellow]警告：無法產生 Apple Music Token（{e}），改用 iTunes Search API[/yellow]")
    return None


def _try_load_cache(
    playlist_name: str,
    output_dir: Path,
) -> "list[MatchResult] | None":
    """若 output_dir 中的 CSV cache 存在且未過期，載入並回傳；否則回傳 None。"""
    from .matcher import MatchResult  # noqa: F401（型別提示用）
    from .exporter import load_from_csv

    safe_name = playlist_name.replace("/", "-").replace("\\", "-")
    csv_path = output_dir / f"{safe_name}.csv"

    if not csv_path.exists():
        return None

    age = time.time() - csv_path.stat().st_mtime
    if age >= _CACHE_TTL:
        console.print(
            f"[dim]Cache 已過期（{age / 60:.0f} 分鐘前），重新比對…[/dim]"
        )
        return None

    console.print(
        f"[green]✓ 使用 cache[/green][dim]（{age / 60:.0f} 分鐘前，有效期 {_CACHE_TTL // 60} 分鐘）[/dim]"
        f"：{csv_path}"
    )
    return load_from_csv(csv_path)


def _match_songs(
    songs: list[Song],
    country: str,
    token: Optional[str],
) -> list[MatchResult]:
    """執行歌曲比對並顯示進度條。"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("比對中...", total=len(songs))

        def on_progress(result: MatchResult) -> None:
            status = "[green]✓[/green]" if result.matched else "[red]✗[/red]"
            progress.update(task, advance=1, description=f"{status} {result.song.name[:30]}")

        return asyncio.run(
            match_all(songs, country=country, on_progress=on_progress, dev_token=token)
        )


def _export_and_push(
    results: list[MatchResult],
    playlist_name: str,
    output_dir: Path,
    token: Optional[str],
    user_token: Optional[str],
    push: bool,
    conflict: str = "new",
    date_suffix: bool = False,
) -> None:
    """輸出比對結果並（若指定）推送至 Apple Music。"""
    matched = sum(1 for r in results if r.matched)
    unmatched = len(results) - matched

    table = Table(title="比對結果摘要")
    table.add_column("項目", style="bold")
    table.add_column("數量", justify="right")
    table.add_row("總歌曲數", str(len(results)))
    table.add_row("成功比對", f"[green]{matched}[/green]")
    table.add_row("未找到", f"[red]{unmatched}[/red]")
    table.add_row("成功率", f"{matched / len(results) * 100:.1f}%")
    console.print(table)

    safe_name = playlist_name.replace("/", "-").replace("\\", "-")
    txt_path = output_dir / f"{safe_name}.txt"
    csv_path = output_dir / f"{safe_name}.csv"
    log_path = output_dir / "unmatched.log"

    txt_count = export_txt(results, txt_path)
    console.print(f"[dim]TXT（{txt_count} 首）：[/dim]{txt_path}")

    export_csv(results, csv_path)
    console.print(f"[dim]CSV 參考：[/dim]{csv_path}")

    if unmatched > 0:
        export_unmatched_log(results, log_path)
        console.print(f"[yellow]未匹配 log：[/yellow]{log_path}")

    if push:
        if not token:
            console.print(
                "[red]錯誤：--push 需要 Apple Developer 憑證（--key-file / --key-id / --team-id）[/red]"
            )
            raise typer.Exit(1)

        if not user_token:
            console.print("\n[bold]需要授權 Apple Music 帳號[/bold]")
            console.print("[dim]即將開啟瀏覽器，請以你的 Apple ID 登入後回到終端機[/dim]")
            try:
                from .auth import get_music_user_token
                user_token = get_music_user_token(token)
                console.print("[green]✓ 授權成功[/green]")
            except TimeoutError as e:
                console.print(f"[red]授權逾時：{e}[/red]")
                raise typer.Exit(1)

        push_name = (
            f"{playlist_name}-{date.today().strftime('%Y%m%d')}"
            if date_suffix else playlist_name
        )
        console.print("\n[bold]推送播放清單至 Apple Music…[/bold]")
        from .pusher import push_to_apple_music

        def _on_push_progress(ok: int, _fail: int) -> None:
            pass

        try:
            _playlist_id, push_ok, push_fail = asyncio.run(
                push_to_apple_music(
                    results, push_name, token, user_token,
                    on_progress=_on_push_progress,
                    conflict=conflict,
                )
            )
            console.print(
                f"[green bold]✓ 已成功推送 {push_ok} 首至 Apple Music 播放清單「{push_name}」[/green bold]"
            )
            if push_fail:
                console.print(
                    f"[yellow]  {push_fail} 首失敗（可能不在台灣 Apple Music 目錄）[/yellow]"
                )
        except Exception as e:
            console.print(f"[red]推送失敗：{e}[/red]")
            raise typer.Exit(1)
    else:
        console.print("[dim]加上 --push 旗標可直接推送至 Apple Music 帳號（需 Apple Developer 憑證）[/dim]")


@app.command()
def auth(
    key_file: Optional[Path] = typer.Option(
        None, "--key-file", "-k",
        help="Apple Developer .p8 私鑰檔路徑",
        envvar="APPLE_KEY_FILE",
    ),
    key_id: Optional[str] = typer.Option(
        None, "--key-id",
        help="Apple Developer Key ID（10 碼）",
        envvar="APPLE_KEY_ID",
    ),
    team_id: Optional[str] = typer.Option(
        None, "--team-id",
        help="Apple Developer Team ID（10 碼）",
        envvar="APPLE_TEAM_ID",
    ),
    dev_token: Optional[str] = typer.Option(
        None, "--dev-token",
        help="直接傳入 Apple Music 開發者 JWT Token",
        envvar="APPLE_DEV_TOKEN",
    ),
) -> None:
    """透過瀏覽器授權取得 Apple Music User Token，並印出供存入 .env 使用。

    取得後將輸出的指令貼到終端機（或寫入 .env）即可啟用無人值守排程。
    """
    token = _get_dev_token(key_file, key_id, team_id, dev_token)
    if not token:
        console.print("[red]錯誤：需要 Apple Developer 憑證（--key-file / --key-id / --team-id 或 .env）[/red]")
        raise typer.Exit(1)

    console.print("[bold]即將開啟瀏覽器，請以你的 Apple ID 登入…[/bold]")
    try:
        from .auth import get_music_user_token
        user_token = get_music_user_token(token)
    except TimeoutError as e:
        console.print(f"[red]授權逾時：{e}[/red]")
        raise typer.Exit(1)

    console.print("\n[green bold]✓ 授權成功！[/green bold]")
    console.print("\n請將以下設定加入 [bold].env[/bold] 檔案：\n")
    console.print(f"[cyan]APPLE_USER_TOKEN={user_token}[/cyan]\n")
    console.print("[dim]設定後執行 chart --push 將直接使用此 token，無需再次授權[/dim]")


@app.command()
def convert(
    kbl_file: Path = typer.Argument(..., help=".kbl 播放清單檔案路徑"),
    output_dir: Path = typer.Option(Path("output"), "--output-dir", "-o", help="輸出目錄"),
    country: str = typer.Option("tw", "--country", "-c", help="iTunes Store 地區代碼"),
    key_file: Optional[Path] = typer.Option(
        None, "--key-file", "-k",
        help="Apple Developer .p8 私鑰檔路徑（用於 Apple Music API，可用 APPLE_KEY_FILE 環境變數）",
        envvar="APPLE_KEY_FILE",
    ),
    key_id: Optional[str] = typer.Option(
        None, "--key-id",
        help="Apple Developer Key ID（10 碼，可用 APPLE_KEY_ID 環境變數）",
        envvar="APPLE_KEY_ID",
    ),
    team_id: Optional[str] = typer.Option(
        None, "--team-id",
        help="Apple Developer Team ID（10 碼，可用 APPLE_TEAM_ID 環境變數）",
        envvar="APPLE_TEAM_ID",
    ),
    dev_token: Optional[str] = typer.Option(
        None, "--dev-token",
        help="直接傳入 Apple Music 開發者 JWT Token（可用 APPLE_DEV_TOKEN 環境變數）",
        envvar="APPLE_DEV_TOKEN",
    ),
    user_token: Optional[str] = typer.Option(
        None, "--user-token",
        help="Apple Music User Token（可用 APPLE_USER_TOKEN 環境變數；未提供時自動開啟瀏覽器授權）",
        envvar="APPLE_USER_TOKEN",
    ),
    push: bool = typer.Option(
        False, "--push",
        help="比對完成後直接透過 Apple Music API 推送至你的帳號（需 Apple Developer 憑證）",
    ),
    conflict: str = typer.Option(
        "new", "--conflict",
        help="同名清單衝突處理：new=建立新清單、replace=刪除舊清單後重建、append=加入現有清單",
    ),
    date_suffix: bool = typer.Option(
        False, "--date-suffix",
        help="在播放清單名稱後加上今天日期，例如「清單名稱-20260430」",
    ),
) -> None:
    """解析 .kbl 並透過 iTunes Search API（或 Apple Music API）比對歌曲。

    使用 Apple Music API 可獲得更精確的歌曲名稱，提高匯入成功率：

        kkbox2applemusic playlist.kbl --key-file AuthKey_XXXXXXXXXX.p8 --key-id XXXXXXXXXX --team-id XXXXXXXXXX
    """
    if not kbl_file.exists():
        console.print(f"[red]錯誤：找不到檔案 {kbl_file}[/red]")
        raise typer.Exit(1)

    token = _get_dev_token(key_file, key_id, team_id, dev_token)
    if not token:
        console.print("[dim]使用 iTunes Search API（免費，無需金鑰）[/dim]")

    console.print(f"[bold]解析[/bold] {kbl_file.name} ...")
    playlist_name, songs = parse_kbl(kbl_file)
    console.print(f"播放清單：[cyan]{playlist_name}[/cyan]，共 [bold]{len(songs)}[/bold] 首歌曲")

    results = _try_load_cache(playlist_name, output_dir)
    if results is None:
        results = _match_songs(songs, country, token)
    _export_and_push(results, playlist_name, output_dir, token, user_token, push, conflict, date_suffix)


# 預定義來源清單（key, 顯示名稱, URL），順序即選單順序
_SOURCES: list[tuple[str, str, str]] = [
    ("daily",      "華語單曲日榜",       "https://kma.kkbox.com/charts/daily/song?cate=297&lang=tc&terr=tw"),
    ("daily-new",  "華語新歌日榜",       "https://kma.kkbox.com/charts/daily/newrelease?terr=tw&lang=tc"),
    ("weekly",     "華語單曲週榜",       "https://kma.kkbox.com/charts/weekly/song?terr=tw&lang=tc"),
    ("weekly-new", "華語新歌週榜",       "https://kma.kkbox.com/charts/weekly/newrelease?terr=tw&lang=tc"),
    ("yearly",     "華語年度單曲累積榜", "https://kma.kkbox.com/charts/yearly/newrelease?lang=tc&terr=tw"),
    ("qiankui",    "錢櫃國語點播榜",     "https://www.kkbox.com/tw/tc/playlist/__u6jEV61Qgdt4Tci1"),
]

_SOURCE_SHORTCUTS: dict[str, str] = {key: url for key, _, url in _SOURCES}


def _show_source_menu() -> str:
    """顯示互動選單，回傳使用者選擇的 URL。"""
    console.print("\n[bold]請選擇來源：[/bold]")
    for i, (key, name, _) in enumerate(_SOURCES, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name}  [dim]({key})[/dim]")
    raw = typer.prompt("\n輸入編號")
    try:
        choice = int(raw)
    except ValueError:
        choice = 0
    if not 1 <= choice <= len(_SOURCES):
        console.print("[red]無效的選項[/red]")
        raise typer.Exit(1)
    _, name, url = _SOURCES[choice - 1]
    console.print(f"已選擇：[cyan]{name}[/cyan]\n")
    return url


@app.command()
def chart(
    source: Optional[str] = typer.Argument(
        None,
        help=(
            "來源代碼或完整 URL。"
            "可用代碼：daily / daily-new / weekly / weekly-new / yearly / qiankui。"
            "省略時顯示互動選單。"
        ),
    ),
    output_dir: Path = typer.Option(Path("output"), "--output-dir", "-o", help="輸出目錄"),
    country: str = typer.Option("tw", "--country", "-c", help="iTunes Store 地區代碼"),
    key_file: Optional[Path] = typer.Option(
        None, "--key-file", "-k",
        help="Apple Developer .p8 私鑰檔路徑",
        envvar="APPLE_KEY_FILE",
    ),
    key_id: Optional[str] = typer.Option(
        None, "--key-id",
        help="Apple Developer Key ID（10 碼）",
        envvar="APPLE_KEY_ID",
    ),
    team_id: Optional[str] = typer.Option(
        None, "--team-id",
        help="Apple Developer Team ID（10 碼）",
        envvar="APPLE_TEAM_ID",
    ),
    dev_token: Optional[str] = typer.Option(
        None, "--dev-token",
        help="直接傳入 Apple Music 開發者 JWT Token",
        envvar="APPLE_DEV_TOKEN",
    ),
    user_token: Optional[str] = typer.Option(
        None, "--user-token",
        help="Apple Music User Token",
        envvar="APPLE_USER_TOKEN",
    ),
    push: bool = typer.Option(
        False, "--push",
        help="比對完成後直接推送至 Apple Music 帳號（需 Apple Developer 憑證）",
    ),
    conflict: str = typer.Option(
        "new", "--conflict",
        help="同名清單衝突處理：new=建立新清單、replace=刪除舊清單後重建、append=加入現有清單",
    ),
    date_suffix: bool = typer.Option(
        False, "--date-suffix",
        help="在播放清單名稱後加上今天日期，例如「清單名稱-20260430」",
    ),
) -> None:
    """從 KKBOX 抓取歌曲，比對並匯入 Apple Music。

    省略來源代碼時顯示互動選單；加代碼或 URL 可直接執行（適合自動化）：

        kkbox2applemusic chart                  # 顯示選單
        kkbox2applemusic chart daily            # 華語單曲日榜
        kkbox2applemusic chart qiankui          # 錢櫃國語點播榜
        kkbox2applemusic chart "https://..."    # 完整 URL
    """
    from .scraper import _PLAYLIST_URL_RE, fetch_chart_songs, fetch_playlist_songs

    if source is None:
        resolved_url = _show_source_menu()
    else:
        resolved_url = _SOURCE_SHORTCUTS.get(source, source)

    is_playlist = bool(_PLAYLIST_URL_RE.search(resolved_url))

    token = _get_dev_token(key_file, key_id, team_id, dev_token)
    if not token:
        console.print("[dim]使用 iTunes Search API（免費，無需金鑰）[/dim]")

    source_label = "播放清單" if is_playlist else "排行榜"
    console.print(f"[bold]抓取{source_label}[/bold] {resolved_url} ...")
    try:
        if is_playlist:
            playlist_name, songs = asyncio.run(fetch_playlist_songs(resolved_url))
        else:
            playlist_name, songs = asyncio.run(fetch_chart_songs(resolved_url))
    except Exception as e:
        console.print(f"[red]錯誤：無法取得{source_label}資料（{e}）[/red]")
        raise typer.Exit(1)

    console.print(f"{source_label}：[cyan]{playlist_name}[/cyan]，共 [bold]{len(songs)}[/bold] 首歌曲")

    if not songs:
        console.print("[yellow]警告：未取得任何歌曲，請確認 URL 是否正確[/yellow]")
        raise typer.Exit(1)

    results = _try_load_cache(playlist_name, output_dir)
    if results is None:
        results = _match_songs(songs, country, token)
    _export_and_push(results, playlist_name, output_dir, token, user_token, push, conflict, date_suffix)
