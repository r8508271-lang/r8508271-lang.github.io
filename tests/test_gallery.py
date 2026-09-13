import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
gallery = importlib.import_module("gallery")
publisher = importlib.import_module("publish")


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "incoming"
        self.source.mkdir()
        self.site = self.root / "site"
        (self.site / "templates").mkdir(parents=True)
        shutil.copyfile(gallery.ROOT / "templates/index.html", self.site / "templates/index.html")

    def entry(self, name="001-private-source-name", filename="video.mp4", description="A title\n\nA useful description."):
        directory = self.source / name
        directory.mkdir(exist_ok=True)
        (directory / filename).write_bytes(b"not yet encoded")
        (directory / "description.txt").write_text(description, encoding="utf-8")
        return directory

    def test_all_input_formats(self):
        for i, filename in enumerate(gallery.MEDIA_NAMES):
            self.entry(str(i), filename)
        self.assertEqual(len(gallery.submissions(self.source)), 4)

    def test_incomplete_and_ambiguous_uploads(self):
        directory = self.entry()
        (directory / "video.gif").write_bytes(b"gif")
        with self.assertRaises(gallery.GalleryError):
            gallery.submissions(self.source)
        (directory / "video.gif").unlink()
        (directory / "description.txt").unlink()
        with self.assertRaises(gallery.GalleryError):
            gallery.submissions(self.source)

    def test_drafts_and_symlinks(self):
        self.entry("_draft")
        self.assertEqual(gallery.submissions(self.source), [])
        (self.source / "bad").symlink_to(self.source / "_draft")
        with self.assertRaises(gallery.GalleryError):
            gallery.submissions(self.source)

    def test_email_drive_link_and_private_paths_blocked(self):
        for text in ["person@example.org", "https://drive.google.com/file/d/private", "/home/person/result", r"C:\Users\person\result"]:
            with self.subTest(text=text), self.assertRaises(gallery.GalleryError):
                gallery.check_public_text(text)

    def test_description_requires_title_and_body(self):
        self.entry(description="Title only")
        with self.assertRaises(gallery.GalleryError):
            gallery.submissions(self.source)

    def test_html_escapes_text(self):
        page = gallery.render([{"id": "abc", "title": '<script>alert("x")</script>',
            "description": '<img src=x onerror=alert(1)>', "src": "media/abc.mp4", "poster": "media/abc.jpg"}],
            "<!-- GALLERY_ENTRIES -->")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<img", page)

    def test_empty_needs_explicit_flag(self):
        (self.site / "index.html").write_text("old gallery")
        with self.assertRaises(gallery.GalleryError):
            gallery.build(self.source, root=self.site)
        self.assertEqual((self.site / "index.html").read_text(), "old gallery")
        self.assertEqual(gallery.build(self.source, root=self.site, allow_empty=True), 0)

    def test_folder_url_validation(self):
        self.assertEqual(gallery.folder_id("https://drive.google.com/drive/u/0/folders/example-ID?usp=sharing"), "example-ID")
        for bad in ["", "https://example.org/folders/example-ID", "../path", "https://drive.google.com/file/d/id"]:
            with self.assertRaises(gallery.GalleryError):
                gallery.folder_id(bad)

    def test_duplicate_drive_names_abort_before_sync(self):
        with patch.object(gallery.shutil, "which", return_value="rclone"), patch.object(gallery, "run", return_value='[{"Path":"same"},{"Path":"same"}]') as run:
            with self.assertRaises(gallery.GalleryError):
                gallery.sync_drive({"drive_folder": "example"}, root=self.site)
            self.assertEqual(run.call_count, 1)

    @unittest.skipUnless(shutil.which("rclone"), "rclone required")
    def test_real_rclone_filter_and_removal(self):
        # A local alias tests rclone traversal/filters without accessing Google.
        self.entry("001", "video.gif")
        self.entry("002", "video.webm")
        self.entry("_draft", "video.mp4")
        (self.source / "001" / "secret.txt").write_text("must stay private")
        config = self.root / "rclone-test.conf"
        config.write_text(f"[test]\ntype = alias\nremote = {self.source}\n")
        settings = {"drive_folder": "example", "rclone_remote": "test", "rclone_config": str(config)}
        cache = gallery.sync_drive(settings, root=self.site)
        self.assertEqual(sorted(str(p.relative_to(cache)) for p in cache.rglob("*") if p.is_file()),
                         ["001/description.txt", "001/video.gif", "002/description.txt", "002/video.webm"])
        shutil.rmtree(self.source / "002")
        gallery.sync_drive(settings, root=self.site)
        self.assertFalse((cache / "002/video.webm").exists())

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_mp4_and_gif_encoding_metadata_audio_and_cache(self):
        mp4 = self.entry("001-private-source-name") / "video.mp4"
        gallery.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=96x64:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=1000", "-t", "0.5", "-c:v", "libx264", "-threads", "1",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-metadata", "artist=PRIVATE_TEST_PERSON", str(mp4)])
        gif = self.entry("002", "video.gif") / "video.gif"
        gallery.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-loop", "0", str(gif)])
        self.assertEqual(gallery.build(self.source, root=self.site), 2)
        page = (self.site / "index.html").read_text()
        self.assertNotIn("private-source-name", page)
        self.assertNotIn(str(self.source), page)
        videos = list((self.site / "media").glob("*.mp4"))
        self.assertEqual(len(videos), 2)
        self.assertEqual(len(list((self.site / "media").glob("*.jpg"))), 2)
        for video in videos:
            result = subprocess.run(["ffmpeg", "-i", str(video)], capture_output=True, text=True)
            self.assertNotIn("PRIVATE_TEST_PERSON", result.stderr)
            self.assertNotIn("Audio:", result.stderr)
            self.assertIn("Video: h264", result.stderr)
            self.assertIn("yuv420p", result.stderr)
        # Nothing is re-encoded on an unchanged rebuild, and output is stable.
        with patch.object(gallery, "run", side_effect=AssertionError("unexpected encoding")):
            gallery.build(self.source, root=self.site)
        self.assertEqual((self.site / "index.html").read_text(), page)
        # A corrupt replacement must preserve the previous gallery and media.
        original_media = {p.name: p.read_bytes() for p in (self.site / "media").iterdir()}
        mp4.write_bytes(b"broken media")
        with self.assertRaises(gallery.GalleryError):
            gallery.build(self.source, root=self.site)
        self.assertEqual((self.site / "index.html").read_text(), page)
        self.assertEqual({p.name: p.read_bytes() for p in (self.site / "media").iterdir()}, original_media)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        publisher.git(self.root, "init", "-b", "main")
        publisher.git(self.root, "config", "core.hooksPath", "/dev/null")
        self.env = {**os.environ, "GIT_AUTHOR_NAME": publisher.NAME, "GIT_AUTHOR_EMAIL": publisher.EMAIL,
                    "GIT_COMMITTER_NAME": publisher.NAME, "GIT_COMMITTER_EMAIL": publisher.EMAIL}

    def commit(self, message="Update gallery", **overrides):
        publisher.git(self.root, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", message,
                      env={**self.env, **overrides})

    def test_empty_and_anonymous_history_pass(self):
        publisher.audit(self.root)
        self.commit()
        publisher.audit(self.root)

    def test_old_personal_author_is_not_hidden_by_new_commit(self):
        self.commit(GIT_AUTHOR_NAME="Personal Name", GIT_AUTHOR_EMAIL="person@example.org")
        self.commit()
        with self.assertRaisesRegex(gallery.GalleryError, "author identity"):
            publisher.audit(self.root)

    def test_committer_and_trailers_are_checked(self):
        self.commit(GIT_COMMITTER_EMAIL="person@example.org")
        with self.assertRaisesRegex(gallery.GalleryError, "committer identity"):
            publisher.audit(self.root)

    def test_identity_trailer_is_blocked(self):
        self.commit("Update gallery\n\nCo-authored-by: Someone <someone@example.org>")
        with self.assertRaisesRegex(gallery.GalleryError, "identity trailer"):
            publisher.audit(self.root)

    def test_non_anonymous_credential_rejected(self):
        with patch.dict(os.environ, {"GALLERY_GITHUB_TOKEN": "test-placeholder"}), patch.object(
            publisher, "github_request", return_value={"login": "different-account", "id": 1}):
            with self.assertRaisesRegex(gallery.GalleryError, "not r8508271-lang"):
                publisher.credential(self.root)

    def test_wrong_remote_rejected(self):
        publisher.git(self.root, "remote", "add", "origin", "https://github.com/another/repo.git")
        with self.assertRaises(gallery.GalleryError):
            publisher.validate_origin(self.root)

    def test_deleted_private_config_still_blocks_history(self):
        private = self.root / ".local/config.json"
        private.parent.mkdir()
        private.write_text('{"drive_folder":"private-example-id"}')
        publisher.git(self.root, "add", ".local/config.json")
        self.commit()
        publisher.git(self.root, "rm", ".local/config.json")
        self.commit()
        with self.assertRaisesRegex(gallery.GalleryError, "private configuration/cache path"):
            publisher.audit(self.root)


if __name__ == "__main__":
    unittest.main()
