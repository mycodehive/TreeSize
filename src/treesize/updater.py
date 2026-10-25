"""GitHub Releases updates with bounded downloads and SHA-256 verification."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .settings import data_directory, normalize_repository

UPDATE_INTERVAL_SECONDS = 4 * 60 * 60
MAX_INSTALLER_BYTES = 1024 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024


class UpdateError(RuntimeError):
    """A safe, user-readable update failure."""


def parse_version(value: str) -> tuple[int, int, int]:
    """Only stable semantic versions are installable; prereleases are ignored."""
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", value.strip())
    if not match:
        raise ValueError("안정 버전은 v1.2.3 형식이어야 합니다.")
    return tuple(int(item) for item in match.groups())


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    notes: str
    url: str
    installer_name: str
    installer_url: str
    checksums_url: str


def _validate_url(url: str, repository: str, *, redirected: bool = False) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UpdateError("업데이트 다운로드 주소가 올바르지 않습니다.") from exc
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or port not in (None, 443) or parsed.fragment):
        raise UpdateError("안전하지 않은 업데이트 다운로드 주소입니다.")
    hostname = (parsed.hostname or "").lower()
    prefix = f"/repos/{repository}/releases/"
    if hostname == "api.github.com" and parsed.path.startswith(prefix):
        return
    if redirected:
        if hostname in {"release-assets.githubusercontent.com", "objects.githubusercontent.com",
                        "github-releases.githubusercontent.com"}:
            return
        if hostname == "github.com" and parsed.path.startswith(f"/{repository}/releases/download/"):
            return
    raise UpdateError("이 저장소의 GitHub 릴리스 주소만 사용할 수 있습니다.")


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, repository: str):
        super().__init__()
        self.repository = repository

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.repository, redirected=True)
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is not None:
            # Even a GitHub-to-GitHub redirect never carries the user's token.
            result.remove_header("Authorization")
            result.remove_header("Proxy-Authorization")
        return result


class GitHubUpdater:
    def __init__(self, repository: str, token: str = ""):
        self.repository = normalize_repository(repository)
        self.token = token.strip()
        if "\r" in self.token or "\n" in self.token:
            raise ValueError("GitHub 토큰 형식이 올바르지 않습니다.")
        self._opener = build_opener(_SafeRedirect(self.repository))

    def _open(self, url: str, *, binary: bool = False):
        _validate_url(url, self.repository)
        request = Request(url, headers={
            "User-Agent": "TreeSizeExplorer-Updater",
            "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            return self._opener.open(request, timeout=30)
        except HTTPError as exc:
            messages = {
                401: "GitHub 인증에 실패했습니다. 설정에서 토큰을 확인하세요.",
                403: "GitHub API 접근이 제한되었습니다. 토큰 권한 또는 요청 제한을 확인하세요.",
                404: "공개된 릴리스가 없거나 비공개 저장소 인증이 필요합니다. 저장소 주소와 Contents 읽기 권한 토큰을 확인하세요.",
                429: "GitHub 요청 제한에 도달했습니다. 나중에 다시 확인하세요.",
            }
            raise UpdateError(messages.get(exc.code, f"GitHub 응답 오류 ({exc.code})")) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise UpdateError("업데이트 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요.") from exc

    def _read(self, url: str, *, binary: bool = False, limit: int = MAX_METADATA_BYTES) -> bytes:
        try:
            with self._open(url, binary=binary) as response:
                result = response.read(limit + 1)
                if len(result) > limit:
                    raise UpdateError("업데이트 정보 파일이 허용 크기를 초과했습니다.")
                return result
        except (OSError, TimeoutError) as exc:
            raise UpdateError("업데이트 정보 다운로드가 중단되었습니다.") from exc

    def check(self, current_version: str) -> Release | None:
        current = parse_version(current_version)
        try:
            payload = json.loads(self._read(f"https://api.github.com/repos/{self.repository}/releases/latest"))
            if not isinstance(payload, dict):
                raise ValueError("Invalid release")
            if payload.get("draft") or payload.get("prerelease"):
                return None
            tag = str(payload.get("tag_name", ""))
            try:
                latest = parse_version(tag)
            except ValueError:
                return None
            if latest <= current:
                return None
            version = ".".join(str(item) for item in latest)
            installer_name = f"TreeSizeExplorer-Setup-{version}.exe"
            assets = payload.get("assets", [])
            if not isinstance(assets, list):
                raise ValueError("Invalid assets")
            by_name = {asset["name"]: asset for asset in assets if isinstance(asset, dict) and "name" in asset}
            installer = str(by_name[installer_name]["url"])
            checksums = str(by_name["SHA256SUMS.txt"]["url"])
            asset_pattern = re.compile(rf"https://api\.github\.com/repos/{re.escape(self.repository)}/releases/assets/\d+")
            if not asset_pattern.fullmatch(installer) or not asset_pattern.fullmatch(checksums):
                raise UpdateError("릴리스의 파일 주소가 올바르지 않습니다.")
            page = str(payload.get("html_url", ""))
            parsed = urlsplit(page)
            if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path.startswith(f"/{self.repository}/releases/tag/"):
                raise UpdateError("릴리스 페이지 주소가 올바르지 않습니다.")
            return Release(version, tag, str(payload.get("body") or ""), page,
                           installer_name, installer, checksums)
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError) as exc:
            raise UpdateError("업데이트 릴리스 정보 또는 설치 파일이 올바르지 않습니다.") from exc

    def download(self, release: Release, progress: Callable[[int, int], None] | None = None) -> Path:
        version = ".".join(map(str, parse_version(release.version)))
        expected_name = f"TreeSizeExplorer-Setup-{version}.exe"
        if release.installer_name != expected_name:
            raise UpdateError("업데이트 설치 파일 이름이 올바르지 않습니다.")
        asset_pattern = re.compile(rf"https://api\.github\.com/repos/{re.escape(self.repository)}/releases/assets/\d+")
        if not asset_pattern.fullmatch(release.installer_url) or not asset_pattern.fullmatch(release.checksums_url):
            raise UpdateError("이 저장소의 릴리스 자산만 다운로드할 수 있습니다.")
        try:
            sums = self._read(release.checksums_url, binary=True, limit=256 * 1024).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UpdateError("SHA256 체크섬 파일 인코딩이 올바르지 않습니다.") from exc
        matches = []
        for line in sums.splitlines():
            match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line.strip())
            if match and match[2] == expected_name:
                matches.append(match[1].lower())
        if len(matches) != 1:
            raise UpdateError("설치 파일의 SHA256 체크섬을 찾을 수 없거나 중복되었습니다.")
        directory = data_directory() / "updates"
        directory.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with self._open(release.installer_url, binary=True) as response:
                try:
                    total = int(response.headers.get("Content-Length", "0"))
                except (TypeError, ValueError):
                    total = 0
                if total < 0 or total > MAX_INSTALLER_BYTES:
                    raise UpdateError("설치 파일 크기가 허용 범위를 벗어났습니다.")
                count = 0
                digest = hashlib.sha256()
                with tempfile.NamedTemporaryFile(dir=directory, prefix="download-", suffix=".part", delete=False) as target:
                    temporary = Path(target.name)
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > MAX_INSTALLER_BYTES:
                            raise UpdateError("설치 파일이 허용 크기를 초과했습니다.")
                        target.write(chunk)
                        digest.update(chunk)
                        if progress:
                            progress(count, total)
                if not count or (total and count != total):
                    raise UpdateError("설치 파일 다운로드가 완료되지 않았습니다.")
                if digest.hexdigest() != matches[0]:
                    raise UpdateError("SHA256 검증에 실패했습니다. 설치 파일은 실행하지 않습니다.")
                final = directory / expected_name
                temporary.replace(final)
                return final
        except (OSError, TimeoutError) as exc:
            raise UpdateError("설치 파일 다운로드 또는 저장에 실패했습니다.") from exc
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
