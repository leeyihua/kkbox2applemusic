"""測試命令列介面：來源選擇、cache、匯出與推送流程。"""

import os
import time
from datetime import date
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from kkbox2applemusic import auth as auth_mod
from kkbox2applemusic import cli
from kkbox2applemusic import pusher as pusher_mod
from kkbox2applemusic import scraper as scraper_mod
from kkbox2applemusic.exporter import export_csv
from kkbox2applemusic.matcher import MatchResult
from kkbox2applemusic.parser import Song

FIXTURE_KBL = Path(__file__).parent / "fixtures" / "sample.kbl"

_SONG_A = Song(name="晴天", artist="周杰倫", album="葉惠美", kkbox_id="1", track_id="")
_SONG_B = Song(name="不存在的歌", artist="無名", album="", kkbox_id="2", track_id="")

_MATCHED = MatchResult(
    song=_SONG_A, matched=True,
    apple_track_id=209908499, apple_track_name="晴天",
    apple_artist="Jay Chou", apple_album="葉惠美", confidence=0.95,
)
_UNMATCHED = MatchResult(song=_SONG_B, matched=False, confidence=0.1)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """清除 .env 載入的 Apple 憑證，並放寬 console 寬度避免中文訊息被折行。"""
    for var in (
        "APPLE_KEY_FILE", "APPLE_KEY_ID", "APPLE_TEAM_ID",
        "APPLE_DEV_TOKEN", "APPLE_USER_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "console", Console(width=300))


@pytest.fixture
def fake_match(monkeypatch):
    """以假的 match_all 取代實際比對，記錄呼叫參數。"""
    calls: list[dict] = []

    async def _fake(songs, country="tw", on_progress=None, dev_token=None):
        calls.append({"songs": songs, "country": country, "dev_token": dev_token})
        results = [
            MatchResult(song=s, matched=(i == 0), apple_track_id=100 + i if i == 0 else None,
                        apple_track_name=s.name if i == 0 else None, confidence=0.9 if i == 0 else 0.1)
            for i, s in enumerate(songs)
        ]
        for r in results:
            if on_progress:
                on_progress(r)
        return results

    monkeypatch.setattr(cli, "match_all", _fake)
    return calls


@pytest.fixture
def fake_chart(monkeypatch):
    """以假的排行榜／playlist 抓取函式取代網路請求，記錄被呼叫的 URL。"""
    calls: dict[str, list[str]] = {"chart": [], "playlist": []}

    async def _chart(url):
        calls["chart"].append(url)
        return "排行榜", [_SONG_A, _SONG_B]

    async def _playlist(url):
        calls["playlist"].append(url)
        return "播放清單", [_SONG_A]

    monkeypatch.setattr(scraper_mod, "fetch_chart_songs", _chart)
    monkeypatch.setattr(scraper_mod, "fetch_playlist_songs", _playlist)
    return calls


@pytest.fixture
def fake_push(monkeypatch):
    """以假的 push_to_apple_music 取代 API 推送，記錄呼叫參數。"""
    calls: list[dict] = []

    async def _push(results, playlist_name, dev_token, user_token, on_progress=None, conflict="new"):
        calls.append({
            "name": playlist_name, "dev_token": dev_token,
            "user_token": user_token, "conflict": conflict,
        })
        ok = sum(1 for r in results if r.matched)
        return "p.NEW", ok, 0

    monkeypatch.setattr(pusher_mod, "push_to_apple_music", _push)
    return calls


# ── _get_dev_token ──────────────────────────────────────────────────────────

def test_get_dev_token_prefers_direct_token():
    assert cli._get_dev_token(Path("x.p8"), "K" * 10, "T" * 10, "direct") == "direct"


def test_get_dev_token_none_without_credentials():
    assert cli._get_dev_token(None, None, None, None) is None


def test_get_dev_token_generates_from_key(monkeypatch):
    monkeypatch.setattr(auth_mod, "generate_developer_token", lambda *a: "jwt")
    assert cli._get_dev_token(Path("k.p8"), "K" * 10, "T" * 10, None) == "jwt"


def test_get_dev_token_falls_back_on_error(tmp_path: Path):
    # 找不到私鑰檔 → 印出警告並回傳 None（改用 iTunes Search API）
    assert cli._get_dev_token(tmp_path / "missing.p8", "K" * 10, "T" * 10, None) is None


# ── _try_load_cache ─────────────────────────────────────────────────────────

def test_cache_missing_returns_none(tmp_path: Path):
    assert cli._try_load_cache("排行榜", tmp_path) is None


def test_cache_fresh_is_loaded(tmp_path: Path):
    export_csv([_MATCHED, _UNMATCHED], tmp_path / "排行榜.csv")

    results = cli._try_load_cache("排行榜", tmp_path)

    assert results is not None
    assert [r.matched for r in results] == [True, False]
    assert results[0].apple_track_id == 209908499


def test_cache_expired_returns_none(tmp_path: Path):
    csv_path = tmp_path / "排行榜.csv"
    export_csv([_MATCHED], csv_path)
    old = time.time() - cli._CACHE_TTL - 60
    os.utime(csv_path, (old, old))

    assert cli._try_load_cache("排行榜", tmp_path) is None


def test_cache_name_with_slash_is_sanitized(tmp_path: Path):
    export_csv([_MATCHED], tmp_path / "A-B.csv")
    assert cli._try_load_cache("A/B", tmp_path) is not None


# ── chart：來源解析 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", [k for k, _, _ in cli._SOURCES if k != "qiankui"])
def test_chart_shortcut_resolves_to_chart_url(key, tmp_path, fake_chart, fake_match):
    result = runner.invoke(cli.app, ["chart", key, "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert fake_chart["chart"] == [cli._SOURCE_SHORTCUTS[key]]
    assert fake_chart["playlist"] == []


def test_chart_playlist_shortcut_uses_playlist_fetcher(tmp_path, fake_chart, fake_match):
    result = runner.invoke(cli.app, ["chart", "qiankui", "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert fake_chart["playlist"] == [cli._SOURCE_SHORTCUTS["qiankui"]]
    assert fake_chart["chart"] == []


def test_chart_full_url_passed_through(tmp_path, fake_chart, fake_match):
    url = "https://kma.kkbox.com/charts/weekly/song?terr=hk&lang=tc"
    result = runner.invoke(cli.app, ["chart", url, "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert fake_chart["chart"] == [url]


def test_chart_menu_selection(tmp_path, fake_chart, fake_match):
    result = runner.invoke(cli.app, ["chart", "-o", str(tmp_path)], input="3\n")

    assert result.exit_code == 0, result.output
    assert fake_chart["chart"] == [cli._SOURCES[2][2]]
    assert "已選擇" in result.output


@pytest.mark.parametrize("choice", ["0", "99", "abc"])
def test_chart_menu_invalid_choice_exits(choice, tmp_path, fake_chart, fake_match):
    result = runner.invoke(cli.app, ["chart", "-o", str(tmp_path)], input=f"{choice}\n")

    assert result.exit_code == 1
    assert "無效的選項" in result.output
    assert fake_chart["chart"] == [] and fake_chart["playlist"] == []


def test_chart_fetch_error_exits(monkeypatch, tmp_path):
    async def _boom(url):
        raise RuntimeError("API 壞了")

    monkeypatch.setattr(scraper_mod, "fetch_chart_songs", _boom)
    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "API 壞了" in result.output


def test_chart_no_songs_exits(monkeypatch, tmp_path, fake_match):
    async def _empty(url):
        return "空榜", []

    monkeypatch.setattr(scraper_mod, "fetch_chart_songs", _empty)
    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "未取得任何歌曲" in result.output
    assert fake_match == []


# ── chart：比對、匯出與 cache ───────────────────────────────────────────────

def test_chart_exports_files(tmp_path, fake_chart, fake_match):
    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path), "-c", "hk"])

    assert result.exit_code == 0, result.output
    assert fake_match[0]["country"] == "hk"
    assert fake_match[0]["dev_token"] is None
    assert (tmp_path / "排行榜.txt").exists()
    assert (tmp_path / "排行榜.csv").exists()
    # 有一首未匹配 → 產生 unmatched.log
    assert (tmp_path / "unmatched.log").exists()
    assert "--push" in result.output  # 未推送時提示可加 --push


def test_chart_uses_cache_and_skips_matching(tmp_path, fake_chart, fake_match):
    export_csv([_MATCHED], tmp_path / "排行榜.csv")

    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert fake_match == []
    assert "使用 cache" in result.output


def test_chart_passes_dev_token_to_matcher(tmp_path, fake_chart, fake_match):
    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path), "--dev-token", "dev"])

    assert result.exit_code == 0, result.output
    assert fake_match[0]["dev_token"] == "dev"


# ── 推送 ────────────────────────────────────────────────────────────────────

def test_push_without_dev_token_exits(tmp_path, fake_chart, fake_match, fake_push):
    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path), "--push"])

    assert result.exit_code == 1
    assert "需要 Apple Developer 憑證" in result.output
    assert fake_push == []


def test_push_with_tokens(tmp_path, fake_chart, fake_match, fake_push):
    result = runner.invoke(cli.app, [
        "chart", "daily", "-o", str(tmp_path), "--push",
        "--dev-token", "dev", "--user-token", "user", "--conflict", "replace",
    ])

    assert result.exit_code == 0, result.output
    assert fake_push == [{
        "name": "排行榜", "dev_token": "dev", "user_token": "user", "conflict": "replace",
    }]
    assert "已成功推送 1 首" in result.output


def test_push_reads_tokens_from_env(monkeypatch, tmp_path, fake_chart, fake_match, fake_push):
    monkeypatch.setenv("APPLE_DEV_TOKEN", "env-dev")
    monkeypatch.setenv("APPLE_USER_TOKEN", "env-user")

    result = runner.invoke(cli.app, ["chart", "daily", "-o", str(tmp_path), "--push"])

    assert result.exit_code == 0, result.output
    assert fake_push[0]["dev_token"] == "env-dev"
    assert fake_push[0]["user_token"] == "env-user"


def test_push_date_suffix(tmp_path, fake_chart, fake_match, fake_push):
    result = runner.invoke(cli.app, [
        "chart", "daily", "-o", str(tmp_path), "--push",
        "--dev-token", "dev", "--user-token", "user", "--date-suffix",
    ])

    assert result.exit_code == 0, result.output
    assert fake_push[0]["name"] == f"排行榜-{date.today():%Y%m%d}"
    # 日期後綴只影響推送名稱，輸出檔名不變
    assert (tmp_path / "排行榜.csv").exists()


def test_push_authorizes_when_no_user_token(monkeypatch, tmp_path, fake_chart, fake_match, fake_push):
    monkeypatch.setattr(auth_mod, "get_music_user_token", lambda dev: f"authorized-{dev}")

    result = runner.invoke(cli.app, [
        "chart", "daily", "-o", str(tmp_path), "--push", "--dev-token", "dev",
    ])

    assert result.exit_code == 0, result.output
    assert fake_push[0]["user_token"] == "authorized-dev"
    assert "授權成功" in result.output


def test_push_authorization_timeout_exits(monkeypatch, tmp_path, fake_chart, fake_match, fake_push):
    def _timeout(dev):
        raise TimeoutError("逾時")

    monkeypatch.setattr(auth_mod, "get_music_user_token", _timeout)
    result = runner.invoke(cli.app, [
        "chart", "daily", "-o", str(tmp_path), "--push", "--dev-token", "dev",
    ])

    assert result.exit_code == 1
    assert "授權逾時" in result.output
    assert fake_push == []


def test_push_failure_exits(monkeypatch, tmp_path, fake_chart, fake_match):
    async def _fail(*args, **kwargs):
        raise RuntimeError("403 無訂閱")

    monkeypatch.setattr(pusher_mod, "push_to_apple_music", _fail)
    result = runner.invoke(cli.app, [
        "chart", "daily", "-o", str(tmp_path), "--push",
        "--dev-token", "dev", "--user-token", "user",
    ])

    assert result.exit_code == 1
    assert "推送失敗" in result.output


# ── convert ─────────────────────────────────────────────────────────────────

def test_convert_missing_file_exits(tmp_path):
    result = runner.invoke(cli.app, ["convert", str(tmp_path / "nope.kbl")])

    assert result.exit_code == 1
    assert "找不到檔案" in result.output


def test_convert_parses_kbl_and_exports(tmp_path, fake_match):
    result = runner.invoke(cli.app, ["convert", str(FIXTURE_KBL), "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert len(fake_match) == 1 and fake_match[0]["songs"]
    assert (tmp_path / "測試播放清單.csv").exists()
    assert (tmp_path / "測試播放清單.txt").exists()


def test_convert_push(tmp_path, fake_match, fake_push):
    result = runner.invoke(cli.app, [
        "convert", str(FIXTURE_KBL), "-o", str(tmp_path), "--push",
        "--dev-token", "dev", "--user-token", "user", "--conflict", "append",
    ])

    assert result.exit_code == 0, result.output
    assert fake_push[0]["name"] == "測試播放清單"
    assert fake_push[0]["conflict"] == "append"


# ── auth ────────────────────────────────────────────────────────────────────

def test_auth_without_credentials_exits():
    result = runner.invoke(cli.app, ["auth"])

    assert result.exit_code == 1
    assert "需要 Apple Developer 憑證" in result.output


def test_auth_prints_user_token(monkeypatch):
    monkeypatch.setattr(auth_mod, "get_music_user_token", lambda dev: "user-xyz")

    result = runner.invoke(cli.app, ["auth", "--dev-token", "dev"])

    assert result.exit_code == 0, result.output
    assert "APPLE_USER_TOKEN=user-xyz" in result.output


def test_auth_timeout_exits(monkeypatch):
    def _timeout(dev):
        raise TimeoutError("逾時")

    monkeypatch.setattr(auth_mod, "get_music_user_token", _timeout)
    result = runner.invoke(cli.app, ["auth", "--dev-token", "dev"])

    assert result.exit_code == 1
    assert "授權逾時" in result.output
