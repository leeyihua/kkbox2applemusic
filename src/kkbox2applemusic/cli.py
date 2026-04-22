"""命令列介面。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from .exporter import export_applescript, export_csv, export_itunes_xml, export_txt, export_unmatched_log
from .matcher import MatchResult, match_all
from .parser import parse_kbl

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

    results: list[MatchResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("比對中...", total=len(songs))

        def on_progress(result: MatchResult) -> None:
            status = "[green]✓[/green]" if result.matched else "[red]✗[/red]"
            progress.update(
                task,
                advance=1,
                description=f"{status} {result.song.name[:30]}",
            )

        results = asyncio.run(
            match_all(songs, country=country, on_progress=on_progress, dev_token=token)
        )

    matched = sum(1 for r in results if r.matched)
    unmatched = len(results) - matched

    # 輸出摘要
    table = Table(title="比對結果摘要")
    table.add_column("項目", style="bold")
    table.add_column("數量", justify="right")
    table.add_row("總歌曲數", str(len(results)))
    table.add_row("成功比對", f"[green]{matched}[/green]")
    table.add_row("未找到", f"[red]{unmatched}[/red]")
    table.add_row("成功率", f"{matched / len(results) * 100:.1f}%")
    console.print(table)

    # 輸出檔案
    safe_name = playlist_name.replace("/", "-").replace("\\", "-")
    txt_path = output_dir / f"{safe_name}.txt"
    csv_path = output_dir / f"{safe_name}.csv"
    log_path = output_dir / "unmatched.log"

    script_path = output_dir / f"{safe_name}.applescript"
    script_count = export_applescript(results, script_path, playlist_name)
    console.print(f"[green]AppleScript（{script_count} 首，建議使用）：[/green]{script_path}")

    xml_path = output_dir / f"{safe_name}.xml"
    xml_count = export_itunes_xml(results, xml_path, playlist_name)
    console.print(f"[dim]XML 備用（{xml_count} 首）：[/dim]{xml_path}")

    txt_count = export_txt(results, txt_path)
    console.print(f"[dim]TXT 備用（{txt_count} 首）：[/dim]{txt_path}")

    export_csv(results, csv_path)
    console.print(f"[dim]CSV 參考：[/dim]{csv_path}")

    if unmatched > 0:
        export_unmatched_log(results, log_path)
        console.print(f"[yellow]未匹配 log：[/yellow]{log_path}")

    # ── 推送至 Apple Music 帳號 ──────────────────────────────────────────────
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

        console.print("\n[bold]推送播放清單至 Apple Music…[/bold]")
        from .pusher import push_to_apple_music

        pushed_count = 0

        def _on_push_progress(ok: int, _fail: int) -> None:
            nonlocal pushed_count
            pushed_count = ok

        try:
            _playlist_id, push_ok, push_fail = asyncio.run(
                push_to_apple_music(
                    results, playlist_name, token, user_token,
                    on_progress=_on_push_progress,
                )
            )
            console.print(
                f"[green bold]✓ 已成功推送 {push_ok} 首至 Apple Music 播放清單「{playlist_name}」[/green bold]"
            )
            if push_fail:
                console.print(
                    f"[yellow]  {push_fail} 首失敗（可能不在台灣 Apple Music 目錄）[/yellow]"
                )
        except Exception as e:
            console.print(f"[red]推送失敗：{e}[/red]")
            raise typer.Exit(1)
    else:
        console.print(
            "\n[bold]匯入建議：[/bold]雙擊 [cyan].applescript[/cyan] 檔案 → Script Editor 開啟 → 按「執行」（Cmd+R）"
        )
        console.print("[dim]或加上 --push 旗標直接推送至 Apple Music 帳號（需 Apple Developer 憑證）[/dim]")
