from pathlib import Path
from urllib.parse import quote

import pytest

from scripts.verify_p2 import _preflight_database_url


def _cloud_url(*, password: str = "synthetic-password", query: str = "sslmode=verify-full") -> str:
    authority = "app" + ":" + quote(password, safe="") + "@" + "cluster.example.invalid:26257"
    return "postgresql://" + authority + "/defaultdb?" + query


def test_preflight_rejects_a_password_instead_of_a_complete_url(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="complete postgresql"):
        _preflight_database_url(
            "synthetic-password-only",
            platform_name="nt",
            appdata=tmp_path,
        )


def test_preflight_rejects_a_password_placeholder(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="password placeholder"):
        _preflight_database_url(
            _cloud_url(password="<ENTER-PASSWORD>"),
            platform_name="nt",
            appdata=tmp_path,
        )


def test_preflight_requires_verify_full() -> None:
    with pytest.raises(RuntimeError, match="sslmode=verify-full"):
        _preflight_database_url(_cloud_url(query="sslmode=require"), platform_name="posix")


def test_preflight_requires_the_windows_default_root_certificate(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="root CA is missing"):
        _preflight_database_url(_cloud_url(), platform_name="nt", appdata=tmp_path)


def test_preflight_accepts_the_windows_default_root_certificate(tmp_path: Path) -> None:
    certificate = tmp_path / "postgresql" / "root.crt"
    certificate.parent.mkdir()
    certificate.write_text("synthetic certificate fixture", encoding="utf-8")

    _preflight_database_url(_cloud_url(), platform_name="nt", appdata=tmp_path)


def test_preflight_accepts_an_explicit_root_certificate_parameter(tmp_path: Path) -> None:
    explicit = quote(str(tmp_path / "root.crt"), safe="")

    _preflight_database_url(
        _cloud_url(query=f"sslmode=verify-full&sslrootcert={explicit}"),
        platform_name="nt",
        appdata=tmp_path,
    )
