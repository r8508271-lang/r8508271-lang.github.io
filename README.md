# Anonymous video gallery

A small, static gallery for an anonymous submission. Each entry is a video with
an accompanying title and paragraph. No JavaScript, external fonts, analytics,
Drive embeds, or server are needed on GitHub Pages.

## 给上传素材的同学

在团队共享的 **gallery 专用 Google Drive 文件夹**内，每个结果建一个子文件夹：

```text
gallery/
  001-hook-as-shovel/
    video.gif
    description.txt
  002-another-result/
    video.mp4
    description.txt
```

- 每个子文件夹只放 **一个**媒体文件，固定命名为 `video.mp4`、`video.gif`、
  `video.webm` 或 `video.mov`。GIF 和视频都支持，发布时统一转换为可播放的 MP4。
- `description.txt` 是 UTF-8 纯文本文件，**第一行是标题，其余内容是说明**。
  不要创建 Google Docs 文档。可复制 `submission-template/example-001/description.txt`。
- 文件夹名必须唯一；按文件夹名称排序，建议用 `001-`、`002-` 前缀。
  公开文件名会替换为哈希，但文件夹仍建议使用中性名称。
- 上传期间，把文件夹命名为 `_draft-001`；媒体和说明都上传完成后，再改为 `001-...`。
  以 `_` 或 `.` 开头的文件夹不会进入 gallery。
- 说明、画面中不要出现作者姓名、单位、邮箱、个人路径或私人链接。文字按纯文本显示。
- 视频发布时会**移除音轨**，适合无解说的实验结果；重要信息请写进说明。

说明文件示例：

```text
Using a hook as a shovel

The agent repurposes an L-shaped hook to scoop, carry, and pour objects.
Watch how it changes the tool orientation to collect and release the load.
```

## 本地配置（只需一次）

需要 Python 3.10+、Git、[FFmpeg](https://ffmpeg.org/download.html) 和
[rclone](https://rclone.org/drive/)。Python 只使用标准库。

```bash
mkdir -p .local
cp config.example.json .local/config.json
```

编辑 `.local/config.json`：填入 **gallery 子文件夹**的 Drive 链接，配置已有的
rclone remote。可复用拉取实验数据时使用的 remote 和配置文件，通过
`rclone_config` 指定其本地路径；`rclone_binary`、`ffmpeg` 也可填可执行文件的绝对路径。
无需公开 Drive 文件夹；只需本地 rclone 登录的 Google 账号有读取权限。

若尚未配置 rclone，运行 `rclone config`，创建 Google Drive remote。
只读权限 `drive.readonly` 足够。按照 rclone 当前文档配置 OAuth client。

`.local/`、Drive 文件夹 ID、原始素材、缓存、rclone token、GitHub token 都留在本地。
**不要把实际配置填写到 `config.example.json`，也不要把 token 放进仓库或聊天。**

## 每次更新

先同步并检查本地页面：

```bash
python3 scripts/gallery.py sync
python3 -m http.server 8000 --bind 127.0.0.1
```

浏览器打开 `http://127.0.0.1:8000`。已有本地素材时，不需要 Drive：

```bash
python3 scripts/gallery.py build --source /path/to/gallery-submissions
```

一条命令完成 **Drive → 本地 → 生成 gallery → 匿名提交 → 推送 GitHub**：

```bash
python3 scripts/gallery.py publish
```

或者发布已经拉取的本地素材：

```bash
python3 scripts/gallery.py publish --source /path/to/gallery-submissions
```

两种方式都可用 `--ffmpeg /path/to/ffmpeg` 覆盖 FFmpeg 路径。
无变化时不创建新提交。更新失败时不会推送；媒体校验或转换失败时保留原有公开页面。
从 Drive 删除条目后，下次成功同步会从当前页面移除，但 **Git 历史仍保留旧版本**。
空文件夹默认报错；只有明确要清空 gallery 时才加 `--allow-empty`。
重复命名、未上传完成的条目或损坏媒体会阻止本次构建，不会静默发布不完整页面。

脚本压缩为最长宽度 1280 的 H.264 MP4，并生成封面图；相同源文件复用本地编码缓存。
页面不自动播放，也不预加载整段视频，手机会自动改成上下布局。
单个输出限制为 95 MiB、整组媒体限制为 900 MiB，为
[GitHub 文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
和 [Pages 的 1 GB 站点上限](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
留出空间。长期大量视频会累积 Git 历史，适合精选的短结果集。

## 匿名提交与部署

**Keep my email addresses private 不会隐藏提交历史，也不会修改旧提交。**
命令行 Git 的 author 和 committer 取决于本地配置，与浏览器登录账号是两件事。
参见 [GitHub 官方说明](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)。

这个仓库固定使用：

```text
name:  Anonymous Authors
email: 328601582+r8508271-lang@users.noreply.github.com
```

在其他电脑克隆仓库后，也设置仓库级身份，避免手工提交误用全局身份：

```bash
git config --local user.name "Anonymous Authors"
git config --local user.email "328601582+r8508271-lang@users.noreply.github.com"
git config --local commit.gpgsign false
git config --local tag.gpgsign false
```

发布命令进一步固定 author/committer 和 UTC 提交时间，并禁用自动签名和提交 hooks，
避免个人签名或自动附加的身份信息。它会获取并检查所有可达的分支/标签历史、作者、
提交者、签名、身份 trailer，以及历史中误提交的 `.local/`、环境配置等私人文件。
即使后来删除了私人配置，旧提交仍会被拦截。浅克隆、非匿名提交或 annotated tags 会阻止发布。
它不会自动重写、强推或删除历史。

推送前，还会调用 GitHub `/user` 验证凭证属于 **r8508271-lang**，并将同一凭证用于推送。
仅将 Git 的邮箱改成匿名邮箱、却继续用实名账号推送，不能通过检查。

可使用 Git 的本地 credential helper 登录匿名账号，或在本地环境变量
`GALLERY_GITHUB_TOKEN` 中提供匿名账号的 token。不要在命令行参数、配置文件或聊天里传 token。
Fine-grained token 至少需要此仓库的 **Contents: Read and write**；如需脚本首次启用
Pages，另需 **Pages: Read and write**。不提供 Pages 权限也可以手工启用。

脚本成功推送后会尝试配置 GitHub Pages。也可以在匿名账号下打开仓库
**Settings → Pages → Deploy from a branch → main → / (root)**。
站点地址为 `https://r8508271-lang.github.io/`，首次部署通常需等待几分钟。

单独检查本地已经获取的历史：

```bash
python3 scripts/gallery.py audit
```

自动检查不能识别画面/文字里的所有作者线索，也不覆盖 GitHub 个人资料、活动、
issue/PR、缓存或 fork。作者仍应检查公开内容；GitHub 和 Google 本身仍知道登录身份。
邮箱隐私不等于绝对匿名。建议匿名账号同时开启 **Keep my email addresses private** 和
**Block command line pushes that expose my email**，并只用匿名账号操作此公开仓库。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

媒体集成测试需要 FFmpeg 位于 `PATH`。测试在临时目录运行，不推送到 GitHub。
