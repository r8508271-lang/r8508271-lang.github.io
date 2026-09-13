"""Repository-specific identity checks and authenticated anonymous publishing."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from gallery import GalleryError, check_public_text, run

ACCOUNT = "r8508271-lang"
NAME = "Anonymous Authors"
EMAIL = "328601582+r8508271-lang@users.noreply.github.com"
REPOSITORY = "r8508271-lang/r8508271-lang.github.io"
REMOTE = "https://github.com/" + REPOSITORY + ".git"
IDENTITIES = {(NAME, EMAIL), (ACCOUNT, EMAIL)}
PUBLIC_PATHS = [".gitignore", ".nojekyll", "README.md", "config.example.json", "index.html",
                "assets", "templates", "scripts", "tests", "submission-template", "media"]


def git(root: Path, *args: str, **kwargs) -> str:
    return run(["git", "-C", str(root), *args], **kwargs)


def has_head(root: Path) -> bool:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def audit(root: Path) -> None:
    """Inspect raw identities (ignoring mailmap), messages, tags and signatures."""
    if git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise GalleryError("Fetch the full repository history before auditing or publishing.")
    # rev-list --all includes every fetched branch and tag, and works on an empty repo.
    commits = git(root, "rev-list", "--all").splitlines()
    for commit in commits:
        raw = git(root, "cat-file", "commit", commit)
        headers, _, message = raw.partition("\n\n")
        for field in ("author", "committer"):
            match = re.search(rf"^{field} (.+) <([^<>]+)> \d+ [+-]\d{{4}}$", headers, re.M)
            if not match or (match.group(1), match.group(2)) not in IDENTITIES:
                raise GalleryError(f"Commit {commit[:12]} has an unapproved {field} identity. Do not push; review its history locally.")
        if "\ngpgsig " in headers:
            raise GalleryError(f"Commit {commit[:12]} has a signature. Review/remove any personal signing identity before publishing.")
        if re.search(r"(?:co-authored-by|signed-off-by|on-behalf-of):", message, re.I):
            raise GalleryError(f"Commit {commit[:12]} contains an identity trailer; review it locally.")
        check_public_text(message)
        paths = git(root, "ls-tree", "-r", "--name-only", "-z", commit).split("\0")
        for path in filter(None, paths):
            parts = Path(path).parts
            if any(part in {".local", "rclone.conf"} or part == ".env" or
                   (part.startswith(".env.") and part != ".env.example") or
                   part.endswith(".local.json") for part in parts):
                raise GalleryError(f"Commit {commit[:12]} contains a private configuration/cache path, even if later deleted. Review the history before publishing.")
    for tag in git(root, "for-each-ref", "--format=%(objecttype)", "refs/tags").splitlines():
        if tag == "tag":
            raise GalleryError("Annotated tags can expose tagger identities. Review them before publishing.")


def validate_origin(root: Path) -> None:
    urls = git(root, "remote", "get-url", "--push", "--all", "origin").splitlines()
    fetch_urls = git(root, "remote", "get-url", "--all", "origin").splitlines()
    if urls != [REMOTE] or fetch_urls != [REMOTE]:
        raise GalleryError("origin must point only to the anonymous HTTPS repository, without embedded credentials.")
    if git(root, "branch", "--show-current").strip() != "main":
        raise GalleryError("Publish from main; no branches or history are rewritten automatically.")


def github_request(path: str, token: str, *, data: dict | None = None, method: str = "GET") -> dict:
    request = urllib.request.Request("https://api.github.com" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "anonymous-gallery-publisher", "Content-Type": "application/json"},
        data=json.dumps(data).encode() if data is not None else None, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def credential(root: Path) -> str:
    token = os.environ.get("GALLERY_GITHUB_TOKEN", "")
    if not token:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
        result = subprocess.run(["git", "-C", str(root), "credential", "fill"],
            input=f"protocol=https\nhost=github.com\nusername={ACCOUNT}\n\n",
            capture_output=True, text=True, env=env)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        token = fields.get("password", "") if result.returncode == 0 else ""
    if not token:
        raise GalleryError("Authenticate Git locally as r8508271-lang, or set GALLERY_GITHUB_TOKEN locally (never paste a token in a chat or commit it). The gallery is ready; nothing was pushed.")
    try:
        profile = github_request("/user", token)
    except (urllib.error.URLError, ValueError):
        raise GalleryError("Could not verify the GitHub credential. Nothing was pushed.") from None
    if profile.get("login") != ACCOUNT or profile.get("id") != 328601582:
        raise GalleryError("The authenticated GitHub account is not r8508271-lang. Switch to the anonymous account before publishing.")
    return token


@contextmanager
def authenticated_git(token: str):
    # Pin the verified credential for fetch/push instead of trusting a different
    # cached credential from a global helper. Secrets never enter command arguments.
    with tempfile.TemporaryDirectory(prefix="gallery-auth-") as temp:
        askpass = Path(temp) / "askpass"
        askpass.write_text('#!/bin/sh\ncase "$1" in\n  *Username*) printf "%s\\n" "$GALLERY_AUTH_USER" ;;\n  *) printf "%s\\n" "$GALLERY_AUTH_TOKEN" ;;\nesac\n')
        askpass.chmod(0o700)
        env = {**os.environ, "GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0",
               "GALLERY_AUTH_USER": ACCOUNT, "GALLERY_AUTH_TOKEN": token,
               "GIT_AUTHOR_NAME": NAME, "GIT_AUTHOR_EMAIL": EMAIL,
               "GIT_COMMITTER_NAME": NAME, "GIT_COMMITTER_EMAIL": EMAIL,
               "GIT_AUTHOR_DATE": f"{int(time.time())} +0000",
               "GIT_COMMITTER_DATE": f"{int(time.time())} +0000"}
        yield env


def publish(root: Path) -> None:
    validate_origin(root)
    token = credential(root)
    with authenticated_git(token) as env:
        opts = ["-c", "credential.helper=", "-c", "core.hooksPath=/dev/null"]
        git(root, *opts, "fetch", "origin", "--prune", "--tags", env=env)
        audit(root)
        remote_main = git(root, "for-each-ref", "--format=%(objectname)", "refs/remotes/origin/main").strip()
        if remote_main:
            ahead = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", remote_main, "HEAD"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ahead.returncode:
                raise GalleryError("Remote main has changes missing locally. Reconcile them first, then rerun publish.")
        # Refuse pre-staged content so an unrelated file can never hitch a ride.
        if git(root, "diff", "--cached", "--name-only").strip():
            raise GalleryError("The index already has staged files. Commit/review or unstage them locally, then rerun publish.")
        for key, value in [("user.name", NAME), ("user.email", EMAIL), ("commit.gpgsign", "false"),
                           ("tag.gpgsign", "false")]:
            git(root, "config", "--local", key, value)
        paths = [p for p in PUBLIC_PATHS if (root / p).exists()]
        git(root, "add", "-A", "--", *paths)
        tracked = git(root, "ls-files", "-z").split("\0")
        for path in filter(None, tracked):
            if path.split("/")[0] not in PUBLIC_PATHS or path.endswith((".pyc", ".local.json")) or "__pycache__" in path:
                raise GalleryError("A private or unexpected path is tracked. Review the index before publishing.")
            full = root / path
            if full.is_symlink():
                raise GalleryError("Do not publish symbolic links.")
            if full.is_file() and full.stat().st_size >= 95 * 1024 * 1024:
                raise GalleryError("A tracked file exceeds 95 MiB.")
        if git(root, "diff", "--cached", "--name-only").strip():
            git(root, *opts, "-c", "commit.gpgsign=false", "commit", "-m", "Update anonymous video gallery", env=env)
        if not has_head(root):
            raise GalleryError("There is no content to publish.")
        audit(root)
        git(root, *opts, "push", "--no-follow-tags", "origin", "HEAD:refs/heads/main", env=env)
    print("Pushed to the anonymous repository with verified anonymous credentials.")
    # Classic Pages needs no workflow and no Drive secret in GitHub Actions.
    try:
        try:
            pages = github_request(f"/repos/{REPOSITORY}/pages", token)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            pages = github_request(f"/repos/{REPOSITORY}/pages", token, method="POST",
                data={"build_type": "legacy", "source": {"branch": "main", "path": "/"}})
        source = pages.get("source", {})
        if pages.get("build_type") != "legacy" or source.get("branch") != "main" or source.get("path") != "/":
            print("Files were pushed. In repository Settings → Pages, choose Deploy from a branch → main → / (root).")
        else:
            print("Pages is configured: https://r8508271-lang.github.io/ (deployment may take a few minutes).")
    except (urllib.error.URLError, ValueError):
        print("Files were pushed. Enable Pages in repository Settings → Pages → Deploy from a branch → main → / (root).")
