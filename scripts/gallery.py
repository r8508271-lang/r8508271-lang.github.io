#!/usr/bin/env python3
"""Build a static anonymous gallery from local folders or a private Drive folder."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = b"gallery-h264-silent-1280-crf24-v1"
MAX_VIDEO = 95 * 1024 * 1024
MAX_GALLERY = 900 * 1024 * 1024
MEDIA_NAMES = ("video.mp4", "video.gif", "video.webm", "video.mov")
PROVENANCE_FIELDS = {"source", "method", "result", "seed", "eval-seed", "episode"}


class GalleryError(RuntimeError):
    pass


def run(command: list[str], **kwargs) -> str:
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode:
        # Third-party stderr can contain local paths, URLs or credentials.
        raise GalleryError(f"{Path(command[0]).name} failed (exit {result.returncode}); no gallery was published.")
    return result.stdout


def folder_id(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    url = urlparse(value)
    match = re.search(r"/folders/([A-Za-z0-9_-]+)(?:/|$)", url.path)
    if url.scheme == "https" and url.hostname == "drive.google.com" and match:
        return match.group(1)
    raise GalleryError("Use a Google Drive folder URL or folder ID.")


def check_public_text(text: str) -> None:
    patterns = [r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
                r"(?:drive|docs)\.google\.com", r"(?:/home/|/Users/|[A-Z]:\\Users\\)"]
    if any(re.search(pattern, text, re.I) for pattern in patterns):
        raise GalleryError("A description contains an email, Drive link or personal filesystem path. Remove it before publishing.")


def parse_description(text: str) -> tuple[str, str, dict[str, str], list[str]]:
    """Keep private provenance separate from the title and public description."""
    lines = text.lstrip("\ufeff").strip().splitlines()
    if len(lines) < 2:
        raise GalleryError("description.txt needs a title on the first line and a description below it.")
    title = lines[0].strip()
    remaining = lines[1:]
    separator = next((i for i, line in enumerate(remaining) if line.strip().lower() == "description:"), None)
    provenance = {}
    if separator is not None:
        for line in remaining[:separator]:
            if not line.strip():
                continue
            key, colon, value = line.partition(":")
            key = key.strip().lower().replace("_", "-")
            if not colon or key not in PROVENANCE_FIELDS or key in provenance:
                raise GalleryError("Before Description:, use one Source/Method/Result/Seed/Eval-seed/Episode field per line. Private metadata will not be published.")
            provenance[key] = value.strip()
        body = "\n".join(remaining[separator + 1:]).strip()
    else:
        # Legacy plain-text entries remain supported, but metadata without a
        # separator must never be mistaken for public prose.
        if any(line.partition(":")[0].strip().lower().replace("_", "-") in PROVENANCE_FIELDS
               and ":" in line for line in remaining):
            raise GalleryError("Add Description: after the provenance fields so internal sources stay private.")
        body = "\n".join(remaining).strip()
    if not title or not body:
        raise GalleryError("description.txt needs a non-empty title and public description.")
    if len(title) > 140 or len(body) > 8000:
        raise GalleryError("Keep the title under 141 characters and the description under 8001 characters.")
    check_public_text(title + "\n" + body)
    warnings = []
    missing = [key for key in ("source", "method", "result", "seed") if not provenance.get(key)]
    if missing:
        warnings.append("recommended provenance fields missing: " + ", ".join(missing))
    method = provenance.get("method", "").lower().replace(" ", "_").replace("-", "_")
    method = {"whitebox": "white_box", "blackbox": "black_box"}.get(method, method)
    if method and method not in {"white_box", "black_box", "genplan"}:
        warnings.append("Method should be white_box, black_box, or genplan")
    for key in ("seed", "eval-seed", "episode"):
        if provenance.get(key) and not provenance[key].isdigit():
            warnings.append(key + " should be an integer; distinguish replicate seed from episode seed")
    return title, body, provenance, warnings


def public_metadata(provenance: dict[str, str]) -> dict[str, str]:
    """Publish only recognized methods and numeric seeds, never source paths."""
    metadata = {}
    method = provenance.get("method", "").lower().replace(" ", "_").replace("-", "_")
    labels = {"white_box": "White box", "whitebox": "White box",
              "black_box": "Black box", "blackbox": "Black box", "genplan": "GenPlan"}
    if method in labels:
        metadata["Method"] = labels[method]
    for key, label in [("seed", "Replicate seed"), ("eval-seed", "Eval seed"), ("episode", "Episode")]:
        value = provenance.get(key, "")
        if re.fullmatch(r"[0-9]{1,40}", value):
            metadata[label] = value
    return metadata


def submissions(source: Path) -> list[tuple[str, str, str, Path, dict[str, str]]]:
    if not source.is_dir() or source.is_symlink():
        raise GalleryError("The source must be an existing, non-symlink directory.")
    result = []
    for directory in sorted(source.iterdir()):
        if directory.name.startswith((".", "_")):
            continue
        if directory.is_symlink():
            raise GalleryError("Symlinks are not allowed in the submissions folder.")
        if not directory.is_dir():
            raise GalleryError("Put each submission in its own subfolder; unexpected file at the source root.")
        description = directory / "description.txt"
        videos = [directory / name for name in MEDIA_NAMES if (directory / name).exists() or (directory / name).is_symlink()]
        if len(videos) != 1:
            raise GalleryError("Each submission needs exactly one video.mp4, video.gif, video.webm or video.mov. Finish the upload or prefix the folder with _.")
        video = videos[0]
        if any(p.is_symlink() or not p.is_file() for p in (description, video)):
            raise GalleryError("A submission is incomplete: every folder needs media and description.txt. Finish it or prefix its folder with _.")
        if description.stat().st_size > 32_000:
            raise GalleryError("description.txt must be smaller than 32 KB.")
        title, body, provenance, warnings = parse_description(description.read_text(encoding="utf-8-sig"))
        for warning in warnings:
            print(f"Note: submission {len(result) + 1}: {warning}.", file=sys.stderr)
        public_id = hashlib.sha256(directory.name.encode()).hexdigest()[:16]
        result.append((public_id, title, body, video, public_metadata(provenance)))
    return result


def digest(path: Path) -> str:
    value = hashlib.sha256(PIPELINE)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def render(entries: list[dict], template: str) -> str:
    sections = []
    for number, item in enumerate(entries, 1):
        title, body = html.escape(item["title"]), html.escape(item["description"])
        fields = "".join(f"<div><dt>{html.escape(key)}</dt><dd>{html.escape(value)}</dd></div>"
                         for key, value in item.get("metadata", {}).items())
        metadata = f'<dl class="metadata">{fields}</dl>' if fields else ""
        sections.append(f'''    <article class="entry" id="result-{item['id']}">
      <video controls playsinline muted preload="none" poster="{item['poster']}" aria-label="{title}">
        <source src="{item['src']}" type="video/mp4">
        Your browser does not support embedded video. <a href="{item['src']}">Download the video</a>.
      </video>
      <div class="entry-copy">
        <p class="entry-number">{number:02d}</p>
        <h2>{title}</h2>
        {metadata}
        <p class="description">{body}</p>
      </div>
    </article>''')
    content = "\n".join(sections)
    if template.count("<!-- GALLERY_ENTRIES -->") != 1:
        raise GalleryError("The HTML template must contain exactly one gallery marker.")
    return template.replace("<!-- GALLERY_ENTRIES -->", content)


def build(source: Path, *, root: Path = ROOT, ffmpeg: str = "ffmpeg", allow_empty: bool = False) -> int:
    items = submissions(source)
    if not items and not allow_empty:
        raise GalleryError("No complete submissions found. Use --allow-empty only to intentionally clear the gallery.")
    cache = root / ".local" / "encoded"
    cache.mkdir(parents=True, exist_ok=True)
    entries = []
    # Encode and validate everything before replacing any public files.
    with tempfile.TemporaryDirectory(prefix="build-", dir=root / ".local") as temp:
        stage = Path(temp)
        media = stage / "media"
        media.mkdir()
        for public_id, title, body, video, metadata in items:
            fingerprint = digest(video)
            filename = fingerprint + ".mp4"
            encoded = cache / filename
            if not encoded.exists():
                if not shutil.which(ffmpeg):
                    raise GalleryError("FFmpeg is required. Install ffmpeg or set ffmpeg in .local/config.json.")
                pending = stage / filename
                input_options = ["-ignore_loop", "1"] if video.suffix == ".gif" else []
                run([ffmpeg, "-nostdin", "-v", "error", "-y", *input_options, "-i", str(video),
                     "-map", "0:v:0", "-map_metadata", "-1", "-map_chapters", "-1",
                     "-an", "-sn", "-dn", "-vf", "scale=min(1280\\,trunc(iw/2)*2):-2,setsar=1",
                     "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-pix_fmt", "yuv420p",
                     "-threads", "2", "-movflags", "+faststart", str(pending)])
                if pending.stat().st_size >= MAX_VIDEO:
                    raise GalleryError("An encoded video exceeds 95 MiB. Shorten it before publishing.")
                pending.replace(encoded)
            if not 0 < encoded.stat().st_size < MAX_VIDEO:
                raise GalleryError("A cached video is empty or too large. Remove .local/encoded and retry.")
            shutil.copyfile(encoded, media / filename)
            poster = cache / (fingerprint + ".jpg")
            if not poster.exists():
                pending_poster = stage / poster.name
                run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(encoded),
                     "-frames:v", "1", "-map_metadata", "-1", "-q:v", "3", str(pending_poster)])
                pending_poster.replace(poster)
            shutil.copyfile(poster, media / poster.name)
            entries.append({"id": public_id, "title": title, "description": body,
                            "metadata": metadata,
                            "src": "media/" + filename, "poster": "media/" + poster.name})
        if sum(p.stat().st_size for p in media.iterdir()) > MAX_GALLERY:
            raise GalleryError("Gallery media exceeds the 900 MiB budget. Reduce the collection before publishing.")
        page = render(entries, (root / "templates/index.html").read_text(encoding="utf-8"))
        (stage / "index.html").write_text(page, encoding="utf-8")
        # The only replaced public outputs are these generated files.
        target_media = root / "media"
        backup = stage / "previous-media"
        if target_media.exists():
            target_media.replace(backup)
        try:
            media.replace(target_media)
            (stage / "index.html").replace(root / "index.html")
        except Exception:
            if target_media.exists():
                shutil.rmtree(target_media)
            if backup.exists():
                backup.replace(target_media)
            raise
    return len(entries)


def sync_drive(config: dict, *, root: Path = ROOT) -> Path:
    identifier = folder_id(config.get("drive_folder", ""))
    remote = config.get("rclone_remote", "gallery-drive").rstrip(":")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", remote):
        raise GalleryError("rclone_remote must be a remote name, without a path.")
    binary = config.get("rclone_binary", "rclone")
    if not shutil.which(binary):
        raise GalleryError("rclone was not found. Configure rclone_binary in .local/config.json.")
    cache = root / ".local" / "drive" / identifier
    cache.mkdir(parents=True, exist_ok=True)
    common = ["--drive-root-folder-id", identifier, "--drive-skip-shortcuts", "--drive-skip-gdocs"]
    if config.get("rclone_config"):
        common += ["--config", str(Path(config["rclone_config"]).expanduser())]
    # Drive allows duplicate names; rclone can otherwise silently select one.
    listing = json.loads(run([binary, "lsjson", remote + ":", "--recursive", *common]))
    paths = [entry["Path"] for entry in listing]
    if len(paths) != len(set(paths)):
        raise GalleryError("Duplicate file or folder names in Drive. Give submissions unique folder names.")
    # The destination is a dedicated ignored cache. Never sync back to Drive.
    filters = ["--filter", "- /_*/**", "--filter", "- **/.*{,/**}"]
    for name in (*MEDIA_NAMES, "description.txt"):
        filters += ["--filter", "+ /*/" + name]
    filters += ["--filter", "- **"]
    run([binary, "sync", remote + ":", str(cache), "--checksum", "--delete-after", *filters, *common])
    return cache


def load_config(root: Path = ROOT) -> dict:
    path = root / ".local/config.json"
    if not path.is_file():
        raise GalleryError("Copy config.example.json to .local/config.json and set drive_folder first.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GalleryError(".local/config.json must contain a JSON object.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "sync", "publish", "audit"])
    parser.add_argument("--source", type=Path, help="Build or publish already-downloaded submissions")
    parser.add_argument("--ffmpeg", help="FFmpeg executable")
    parser.add_argument("--allow-empty", action="store_true", help="Intentionally publish an empty gallery")
    parser.add_argument("--scheduled", action="store_true", help="Skip unchanged content and limit automatic publishing to once per 10 minutes")
    args = parser.parse_args()
    from publish import audit, publish, check_scheduled_tree
    # Prevent two local sync/build/publish processes from racing.
    (ROOT / ".local").mkdir(exist_ok=True)
    lock = (ROOT / ".local/run.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.exit(0 if args.scheduled else 1, "Another gallery command is running; skipped.\n")
    try:
        if args.scheduled:
            if args.command != "publish" or args.allow_empty:
                raise GalleryError("--scheduled requires publish and cannot clear an empty gallery.")
            check_scheduled_tree(ROOT)
        if args.command == "audit":
            audit(ROOT)
            print("Commit identities and messages passed the automatic audit. Review visible content separately.")
            return
        if args.command == "sync" and args.source:
            raise GalleryError("sync reads Drive; use build or publish with --source for local submissions.")
        config = {} if args.source else load_config()
        source = args.source if args.source else sync_drive(config)
        count = build(source, ffmpeg=args.ffmpeg or config.get("ffmpeg", "ffmpeg"), allow_empty=args.allow_empty)
        print(f"Built {count} videos. Preview with: python3 -m http.server 8000 --bind 127.0.0.1")
        if args.command == "publish":
            publish(ROOT, scheduled=args.scheduled)
    except (GalleryError, OSError, ValueError, KeyError) as error:
        # OSError can include private absolute paths; details remain local.
        message = str(error) if isinstance(error, GalleryError) else "Invalid configuration, submission data or local file operation. Check the input and retry."
        parser.exit(1, message + "\n")
    finally:
        lock.close()


if __name__ == "__main__":
    # publish imports the shared exception and helpers from this module.
    sys.modules["gallery"] = sys.modules[__name__]
    main()
