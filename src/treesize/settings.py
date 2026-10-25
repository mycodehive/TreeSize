"""User settings and OS-backed credentials. Tokens never enter settings.json."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

DEFAULT_REPOSITORY = "mycodehive/TreeSize"
APP_NAME = "TreeSizeExplorer"


def normalize_repository(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment:
            raise ValueError("GitHub 저장소 주소(owner/repository)를 입력하세요.")
        value = parsed.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}", value):
        raise ValueError("GitHub 저장소는 owner/repository 형식이어야 합니다.")
    owner, repo = value.split("/")
    if repo in {".", ".."}:
        raise ValueError("올바른 GitHub 저장소를 입력하세요.")
    return f"{owner}/{repo}"


def data_directory() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


@dataclass
class Settings:
    repository: str = DEFAULT_REPOSITORY
    check_updates: bool = True


def load_settings() -> Settings:
    try:
        raw = json.loads((data_directory() / "settings.json").read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return Settings()
        return Settings(normalize_repository(raw.get("repository", DEFAULT_REPOSITORY)),
                        raw.get("check_updates", True) is not False)
    except (OSError, ValueError, TypeError, AttributeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    settings.repository = normalize_repository(settings.repository)
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory,
                                     prefix="settings-", suffix=".tmp", delete=False) as stream:
        name = Path(stream.name)
        json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
    try:
        name.replace(directory / "settings.json")
    finally:
        name.unlink(missing_ok=True)


def _credential_backend():
    try:
        if os.name != "nt":
            raise RuntimeError("GitHub 토큰 저장은 Windows 자격 증명 관리자에서 지원합니다.")
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()
    except ImportError as exc:
        raise RuntimeError("자격 증명 저장 모듈이 없습니다. keyring 패키지를 설치하세요.") from exc


def get_token(repository: str) -> str:
    repository = normalize_repository(repository)
    try:
        return _credential_backend().get_password(APP_NAME, repository.lower()) or ""
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Windows 자격 증명 관리자에서 GitHub 토큰을 읽지 못했습니다.") from exc


def set_token(repository: str, token: str) -> None:
    repository = normalize_repository(repository)
    token = token.strip()
    if "\r" in token or "\n" in token:
        raise ValueError("GitHub 토큰에는 줄바꿈이 포함될 수 없습니다.")
    try:
        backend = _credential_backend()
        if token:
            backend.set_password(APP_NAME, repository.lower(), token)
        elif backend.get_password(APP_NAME, repository.lower()):
            backend.delete_password(APP_NAME, repository.lower())
    except (RuntimeError, ValueError):
        raise
    except Exception as exc:
        raise RuntimeError("Windows 자격 증명 관리자에 GitHub 토큰을 저장하지 못했습니다.") from exc
