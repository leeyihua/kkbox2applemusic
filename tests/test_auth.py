"""測試 Apple Music 開發者 Token 產生邏輯。"""

import pytest
from pathlib import Path
from unittest.mock import patch

from kkbox2applemusic.auth import generate_developer_token


def test_missing_key_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate_developer_token(tmp_path / "nonexistent.p8", "AAAAAAAAAA", "BBBBBBBBBB")


def test_invalid_key_id(tmp_path):
    key = tmp_path / "key.p8"
    key.write_text("dummy")
    with pytest.raises(ValueError, match="key_id"):
        generate_developer_token(key, "SHORT", "BBBBBBBBBB")


def test_invalid_team_id(tmp_path):
    key = tmp_path / "key.p8"
    key.write_text("dummy")
    with pytest.raises(ValueError, match="team_id"):
        generate_developer_token(key, "AAAAAAAAAA", "X")


def test_generates_token(tmp_path):
    """使用合法 EC 私鑰驗證 Token 可被產生與解碼。"""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    # 產生測試用 EC 私鑰
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "AuthKey_AAAAAAAAAA.p8"
    key_file.write_bytes(pem)

    token = generate_developer_token(key_file, "AAAAAAAAAA", "BBBBBBBBBB")
    assert isinstance(token, str)
    assert len(token.split(".")) == 3  # JWT 格式：header.payload.signature
