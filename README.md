# Anonymous video gallery

A small, static gallery for an anonymous submission. Each entry is a video with
an accompanying title and paragraph. No JavaScript, external fonts, analytics,
Drive embeds, or server are needed on GitHub Pages.

## Contributing examples

Create one subfolder per example in the team's shared **Google Drive folder
dedicated to the gallery**:

```text
gallery/
  001-hook-as-shovel/
    video.gif
    description.txt
  002-another-result/
    video.mp4
    description.txt
```

- Include exactly **one** media file in each subfolder, named `video.mp4`,
  `video.gif`, `video.webm`, or `video.mov`. Both GIFs and videos are supported;
  all media is converted to a playable MP4 when published.
- Use a UTF-8 plain-text file named `description.txt`. **The first line is the
  title, followed by source metadata; the website description goes after
  `Description:`.** Do not create a Google Docs document. Copy
  `submission-template/example-001/description.txt` as a starting point.
- Folder names must be unique. Entries are sorted by folder name, so prefixes
  such as `001-` and `002-` are useful. Public filenames are replaced with hashes,
  but folder names should still be neutral.
- While uploading, name the folder `_draft-001`. Rename it to `001-...` once both
  the media and description have finished uploading. Folders beginning with `_`
  or `.` are excluded from the gallery.
- Keep author names, affiliations, email addresses, personal paths, and private
  links out of the visible description and video frames. Descriptions are
  displayed as plain text.
- **Audio tracks are removed** during publication. This workflow is intended for
  experiment videos without narration; put important information in the description.

Example description file:

```text
Using a hook as a shovel

Source: results/environment/run/replicate_42/videos/episode_3.gif
Method: white_box
Result: environment/run/replicate_42
Seed: 42
Eval-seed: 123456
Episode: 3

Description:
The agent repurposes an L-shaped hook to scoop, carry, and pour objects.
Watch how it changes the tool orientation to collect and release the load.
```

The numbers and paths above are placeholders. Replace them with the actual
source information. Include these fields in each TXT file whenever possible:

- `Source`: the original media path or an internal team link that identifies the file.
- `Method`: `white_box`, `black_box`, or `genplan`.
- `Result`: the specific experiment/run identifier, preferably including the run
  timestamp and replicate directory.
- `Seed`: the replicate seed used for training or policy synthesis.
- `Eval-seed`: the seed for the individual evaluation episode shown in the video,
  if available. Do not confuse it with the evaluation suite's base seed.
- `Episode`: the episode number used in the source filename, usually starting at 0.

These fields are recommended: missing fields produce warnings without blocking
the build. The older "title + description" format is still supported. When source
metadata is present, a standalone `Description:` line is required to separate the
public text and prevent accidental publication of internal source information.
The website shows the title, `Method`, `Seed` (labeled Replicate seed),
`Eval-seed`, `Episode`, and description. Methods are displayed only as White box,
Black box, or GenPlan; seeds and episode numbers are displayed only if valid integers.
**The original `Source` and `Result` paths stay in the Drive TXT files and local
cache; they are not included in public HTML or Git history.**
GIF, MP4, MOV, and WebM submissions all use this format.

## One-time local setup

Install Python 3.10+, Git, [FFmpeg](https://ffmpeg.org/download.html), and
[rclone](https://rclone.org/drive/). The Python scripts use only the standard library.

```bash
mkdir -p .local
cp config.example.json .local/config.json
```

Edit `.local/config.json`: enter the Drive link for the **gallery subfolder** and
configure an existing rclone remote. You can reuse the remote and configuration
used to download experiment data by setting `rclone_config` to the local config
path. `rclone_binary` and `ffmpeg` also accept absolute executable paths.
The Drive folder does not need to be public; the Google account used by the local
rclone connection only needs read access.

If rclone is not configured yet, run `rclone config` and create a Google Drive
remote. The read-only `drive.readonly` scope is sufficient. Follow the current
rclone documentation to configure an OAuth client.

Keep `.local/`, the Drive folder ID, original media, caches, rclone tokens, and
GitHub tokens local. **Do not put real configuration in `config.example.json`,
or include tokens in the repository or a chat.**

## Updating the gallery

Sync the files and inspect the local page first:

```bash
python3 scripts/gallery.py sync
python3 -m http.server 8000 --bind 127.0.0.1
```

Open `http://127.0.0.1:8000` in a browser. If the submissions are already local,
you can build without Drive:

```bash
python3 scripts/gallery.py build --source /path/to/gallery-submissions
```

One command handles **Drive → local files → gallery build → anonymous commit →
GitHub push**:

```bash
python3 scripts/gallery.py publish
```

Or publish submissions that have already been downloaded:

```bash
python3 scripts/gallery.py publish --source /path/to/gallery-submissions
```

Both commands accept `--ffmpeg /path/to/ffmpeg` to override the executable path.
Unchanged content does not create a new commit. Failed updates are not pushed;
media validation or conversion failures preserve the existing public page.
Deleting an entry from Drive removes it from the current page after the next
successful sync, but **older versions remain in Git history**.
An empty submissions folder is an error by default; add `--allow-empty` only when
intentionally clearing the gallery. Duplicate names, incomplete uploads, or corrupt
media block the build rather than silently publishing an incomplete gallery.

The script encodes H.264 MP4 files at a maximum width of 1280 pixels and generates
poster images. Identical source files reuse the local encoding cache. Videos do
not autoplay or preload the entire file. The layout uses three cards per row on
desktop, two on medium screens, and one on mobile.
Each encoded video must be smaller than 95 MiB, and the media collection is limited
to 900 MiB, leaving room under the
[GitHub file limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
and the [1 GB Pages site limit](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
Video files accumulate in Git history over time, so this repository is best suited
to a curated collection of short examples.

## Automatic local updates every minute (no GPT required)

On Linux, first run and verify `python3 scripts/gallery.py publish` manually, then
install the user-level systemd timer:

```bash
python3 scripts/install_timer.py
```

The timer runs `python3 scripts/gallery.py publish --scheduled` directly. It does
not call GPT, Codex, or any other model, and Codex does not need to remain open.
The computer must be awake and online, with the user's systemd session running.
Checks pause during sleep and resume afterward. The timer reuses the verified
local credentials and configuration, and writes logs to the local journal.

Drive is checked every minute. If nothing has changed, GitHub authentication,
committing, and deployment are skipped. When there are changes, automatic
publications are spaced at least 10 minutes apart; changes received during that
interval are combined in the next publication. This leaves room under the
[GitHub Pages soft limit of 10 builds per hour](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
A manual `publish` runs immediately and restarts the automatic publication interval.
Incomplete uploads, invalid media, or uncommitted local source edits cause that
run to fail and be logged; the next run retries. The timer does not edit source
code or overwrite remote history. The process lock is released when the command exits.

```bash
# Inspect the timer and recent logs
systemctl --user status anonymous-gallery-sync.timer
journalctl --user -u anonymous-gallery-sync.service -n 30 --no-pager

# Stop future checks (a run already in progress will finish)
systemctl --user disable --now anonymous-gallery-sync.timer

# Resume automatic checks
systemctl --user enable --now anonymous-gallery-sync.timer
```

## Anonymous commits and deployment

**Keep my email addresses private does not hide commit history or change old commits.**
The author and committer used by command-line Git depend on local configuration,
separately from the account signed into the browser. See
[GitHub's documentation](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address).

This repository uses the following identity:

```text
name:  Anonymous Authors
email: 328601582+r8508271-lang@users.noreply.github.com
```

After cloning on another computer, also set the repository-specific identity so
manual commits do not accidentally use a global identity:

```bash
git config --local user.name "Anonymous Authors"
git config --local user.email "328601582+r8508271-lang@users.noreply.github.com"
git config --local commit.gpgsign false
git config --local tag.gpgsign false
```

The publish command pins the author and committer identities, uses UTC commit
timestamps, and disables automatic signing and commit hooks to avoid personal
signatures or automatically appended identity information. It fetches and audits
all reachable branch/tag history, authors, committers, signatures, identity
trailers, and accidentally committed private files such as `.local/` and
environment configuration. A private configuration file in an old commit blocks
publication even if it was later deleted. Shallow clones, non-anonymous commits,
and annotated tags also block publication. The script does not automatically
rewrite, force-push, or delete history.

Before pushing, the script calls GitHub's `/user` endpoint to verify that the
credential belongs to **r8508271-lang**, then uses that same credential for the
push. Changing only the Git email address while continuing to push with a personal
account does not pass this check.

Authenticate the anonymous account using Git's local credential helper, or provide
its token through the local `GALLERY_GITHUB_TOKEN` environment variable. Do not
pass tokens in command-line arguments, configuration files, or chats.
A fine-grained token needs at least **Contents: Read and write** for this repository.
To let the script enable Pages for the first time, also grant **Pages: Read and write**.
Without the Pages permission, Pages can be enabled manually instead.

After a successful push, the script attempts to configure GitHub Pages. You can
also sign into the anonymous account and open the repository's
**Settings → Pages → Deploy from a branch → main → / (root)**.
The site is hosted at `https://r8508271-lang.github.io/`; the first deployment
usually takes a few minutes.

To audit history already fetched locally:

```bash
python3 scripts/gallery.py audit
```

The automatic audit cannot detect every author clue in video frames or text. It
also does not cover GitHub profiles, activity, issues/PRs, caches, or forks.
Authors should still review public content; GitHub and Google themselves still
know which accounts are signed in. Email privacy does not provide absolute
anonymity. Enable both **Keep my email addresses private** and **Block command line
pushes that expose my email** on the anonymous account, and use only that account
to work with this public repository.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

Media integration tests require FFmpeg on `PATH`. Tests run in temporary directories
and do not push to GitHub.
