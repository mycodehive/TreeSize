from __future__ import annotations

from dataclasses import replace
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from treesize import settings
from treesize.updater import (GitHubUpdater, Release, UPDATE_INTERVAL_SECONDS,
                              UpdateError, _SafeRedirect, parse_version)


REPO = "mycodehive/TreeSize"
API = f"https://api.github.com/repos/{REPO}/releases/assets/"


class Response(BytesIO):
    def __init__(self, content: bytes, length: int | None = None):
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content) if length is None else length)}


def release_payload():
    return {
        "tag_name": "v1.10.0", "draft": False, "prerelease": False,
        "body": "Release notes", "html_url": f"https://github.com/{REPO}/releases/tag/v1.10.0",
        "assets": [
            {"name": "TreeSizeExplorer-Setup-1.10.0.exe", "url": API + "1"},
            {"name": "SHA256SUMS.txt", "url": API + "2"},
        ],
    }


class VersionTests(unittest.TestCase):
    def test_numeric_comparison(self):
        self.assertGreater(parse_version("v1.10.0"), parse_version("1.9.9"))
        self.assertEqual(parse_version("1.2.3+build.8"), (1, 2, 3))
        self.assertEqual(UPDATE_INTERVAL_SECONDS, 14400)

    def test_reject_prerelease_and_malformed(self):
        for version in ["1.0", "latest", "v1.0.0-rc.1", "1.01.0", "1.2.3.4", "1.2.3+.", "1.2.3+build..8"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                parse_version(version)

    def test_repository_normalization(self):
        self.assertEqual(settings.normalize_repository("https://github.com/mycodehive/TreeSize.git"), REPO)
        for repo in ["../../other", "https://evil.test/a/b", "a/b/c", "a/..", "a/b?x=y", "https://github.com/a/b?q=1"]:
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                settings.normalize_repository(repo)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.updater = GitHubUpdater(REPO, "secret")

    def set_payload(self, payload):
        self.updater._read = Mock(return_value=json.dumps(payload).encode())

    def test_new_stable_release(self):
        self.set_payload(release_payload())
        release = self.updater.check("1.9.9")
        self.assertEqual(release.version, "1.10.0")
        self.assertEqual(release.installer_url, API + "1")
        self.assertIsNone(self.updater.check("1.10.0"))
        self.assertIsNone(self.updater.check("2.0.0"))

    def test_ignore_drafts_and_prereleases(self):
        for changes in [{"draft": True}, {"prerelease": True}, {"tag_name": "v2.0.0-beta.1"}]:
            payload = release_payload() | changes
            self.set_payload(payload)
            self.assertIsNone(self.updater.check("1.0.0"))

    def test_reject_wrong_repository_asset_or_page(self):
        payload = release_payload()
        payload["assets"][0]["url"] = "https://api.github.com/repos/attacker/other/releases/assets/1"
        self.set_payload(payload)
        with self.assertRaises(UpdateError):
            self.updater.check("1.0.0")
        payload = release_payload() | {"html_url": "https://evil.test"}
        self.set_payload(payload)
        with self.assertRaises(UpdateError):
            self.updater.check("1.0.0")

    def test_missing_assets_fails(self):
        self.set_payload(release_payload() | {"assets": []})
        with self.assertRaises(UpdateError):
            self.updater.check("1.0.0")

    def test_authenticated_api_request(self):
        self.updater._opener = Mock()
        self.updater._open(API + "1", binary=True)
        req = self.updater._opener.open.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer secret")
        self.assertEqual(req.get_header("Accept"), "application/octet-stream")

    def test_errors_do_not_expose_credentials(self):
        for failure in [HTTPError(API, 404, "not found", {}, None), URLError("network down")]:
            self.updater._opener = Mock()
            self.updater._opener.open.side_effect = failure
            with self.assertRaises(UpdateError) as raised:
                self.updater._open(API + "1")
            self.assertNotIn("secret", str(raised.exception))
        self.updater._opener.open.side_effect = HTTPError(API, 404, "not found", {}, None)
        with self.assertRaisesRegex(UpdateError, "비공개"):
            self.updater._open(API + "1")

    def test_redirect_strips_authorization(self):
        handler = _SafeRedirect(REPO)
        req = Request(API + "1", headers={"Authorization": "Bearer secret"})
        redirected = handler.redirect_request(req, None, 302, "Found", {},
                     "https://release-assets.githubusercontent.com/github-production-release-asset/1?sig=x")
        self.assertIsNone(redirected.get_header("Authorization"))
        for target in ["http://release-assets.githubusercontent.com/x", "https://evil.test/x",
                       "https://api.github.com/repos/attacker/repo/releases/assets/1"]:
            with self.subTest(target=target), self.assertRaises(UpdateError):
                handler.redirect_request(req, None, 302, "Found", {}, target)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.patch_dir = patch("treesize.updater.data_directory", return_value=self.path)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)
        self.updater = GitHubUpdater(REPO)
        self.release = Release("1.10.0", "v1.10.0", "", f"https://github.com/{REPO}/releases/tag/v1.10.0",
                               "TreeSizeExplorer-Setup-1.10.0.exe", API + "1", API + "2")
        self.content = b"MZ" + b"example Windows installer" * 100

    def supply(self, checksum=None, length=None):
        digest = checksum or hashlib.sha256(self.content).hexdigest()
        self.updater._read = Mock(return_value=f"{digest}  {self.release.installer_name}\n".encode())
        self.updater._open = Mock(return_value=Response(self.content, length))

    def test_download_verified_atomic_file(self):
        self.supply()
        progress = Mock()
        result = self.updater.download(self.release, progress)
        self.assertEqual(result.read_bytes(), self.content)
        self.assertEqual(list(result.parent.glob("*.part")), [])
        progress.assert_called()

    def test_wrong_hash_deletes_partial(self):
        self.supply("0" * 64)
        with self.assertRaisesRegex(UpdateError, "SHA256"):
            self.updater.download(self.release)
        self.assertEqual(list((self.path / "updates").iterdir()), [])

    def test_incomplete_stream_rejected(self):
        self.supply(length=len(self.content) + 100)
        with self.assertRaisesRegex(UpdateError, "완료"):
            self.updater.download(self.release)
        self.assertEqual(list((self.path / "updates").iterdir()), [])

    def test_oversized_stream_rejected(self):
        self.supply()
        with patch("treesize.updater.MAX_INSTALLER_BYTES", 10), self.assertRaises(UpdateError):
            self.updater.download(self.release)

    def test_duplicate_checksum_rejected(self):
        self.supply()
        self.updater._read.return_value *= 2
        with self.assertRaisesRegex(UpdateError, "중복"):
            self.updater.download(self.release)

    def test_wrong_name_and_asset_rejected_before_network(self):
        self.supply()
        for release in [replace(self.release, installer_name="../outside.exe"),
                        replace(self.release, installer_url="https://evil.test/setup.exe")]:
            with self.subTest(release=release), self.assertRaises(UpdateError):
                self.updater.download(release)
        self.updater._open.assert_not_called()


class SettingsTests(unittest.TestCase):
    def test_atomic_settings_without_token(self):
        with tempfile.TemporaryDirectory() as directory, patch("treesize.settings.data_directory", return_value=Path(directory)):
            settings.save_settings(settings.Settings("example/releases", False))
            self.assertEqual(settings.load_settings(), settings.Settings("example/releases", False))
            raw = (Path(directory) / "settings.json").read_text()
            self.assertNotIn("token", raw)
            (Path(directory) / "settings.json").write_text("broken")
            self.assertEqual(settings.load_settings(), settings.Settings())

    def test_credentials_use_os_backend(self):
        backend = Mock()
        backend.get_password.return_value = "secret"
        with patch("treesize.settings._credential_backend", return_value=backend):
            self.assertEqual(settings.get_token(REPO), "secret")
            settings.set_token(REPO, "new-secret")
            backend.set_password.assert_called_once_with("TreeSizeExplorer", REPO.lower(), "new-secret")
            settings.set_token(REPO, "")
            backend.delete_password.assert_called_once_with("TreeSizeExplorer", REPO.lower())


if __name__ == "__main__":
    unittest.main()
