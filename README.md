# MarkItDown First

**Claude reads your documents as Markdown, not as page images or raw Office XML.**

Before Claude touches a PDF, Word, PowerPoint, Excel, EPUB, HTML, Outlook or notebook file, this plugin converts it with Microsoft [markitdown](https://github.com/microsoft/markitdown). Claude then works from a compact `.md` copy that keeps headings, lists and tables.

| File | Original | Markdown Claude reads |
|---|---|---|
| `test.pdf` (research paper) | 91 KB | 5.1 KB |
| `test.docx` | 133 KB | 4.6 KB |
| `test.pptx` | 271 KB | 2.0 KB |
| `test.xlsx` | 11 KB | 0.8 KB |

*Measured on markitdown's own test fixtures.*

## Quick start (step by step)

**Before you start:** you need [Claude Code](https://code.claude.com) and Python 3.10 or newer. Check with `claude --version` and `python3 --version`.

### 1. Install the plugin (one time only)

1. **Open a terminal.**
   - macOS: press `Cmd + Space`, type **Terminal**, press Enter.
   - Windows: open **Git Bash**.
   - Linux: open your terminal app.
2. **Go to a project folder**, for example `cd ~/Documents`.
3. **Start Claude Code** by running `claude`.
4. **Add this repo as a plugin source.** Type this inside Claude:
   ```text
   /plugin marketplace add wrteam-vimal/markitdown-first
   ```
5. **Install the plugin:**
   ```text
   /plugin install markitdown-first@markitdown-first
   ```
6. **Restart Claude.** Type `/exit`, then run `claude` again.
7. **Wait about 2 minutes the first time.** markitdown installs in the background, and this happens only once. Files read before it finishes are read normally.

### 2. Check that it works

8. **Give Claude a document.** Drag a PDF, Word or Excel file into the terminal window to paste its path, then add your question:
   ```text
   Summarize /path/to/report.pdf
   ```
9. **Look for the sign that it converted.** Claude mentions a `.md` file inside a `.markitdown-cache/` folder. If you ask *"did markitdown-first convert it?"*, Claude will say yes.

### 3. Choose what gets converted (optional)

10. **Open the picker:**
    ```text
    /markitdown-first:config
    ```
    Tick the file types you want, then choose **All my projects** or **This project only**.
11. **Shortcuts if you don't want the picker:**
    ```text
    /markitdown-first:config show            # see current settings
    /markitdown-first:config exclude excel   # stop converting Excel
    /markitdown-first:config off             # pause the plugin
    /markitdown-first:config on              # turn it back on
    ```
12. **Pick specific files to convert:**
    ```text
    /markitdown-first:convert
    ```
    Claude lists the documents in the folder and lets you tick which ones to convert.

### 4. Use it in the Claude app on claude.ai (optional)

13. **Build the skill file.** In a terminal (not inside Claude), run:
    ```bash
    git clone https://github.com/wrteam-vimal/markitdown-first.git
    cd markitdown-first
    ./build/build-skill-zip.sh
    ```
    This creates `dist/markitdown-first-skill.zip`.
14. **Upload it.** On claude.ai, go to **Settings → Capabilities → Skills** and upload the zip. After that, Claude converts uploaded documents to Markdown before it answers.

### If something goes wrong

| Problem | Fix |
|---|---|
| Nothing seems to convert | Wait the 2 minutes from step 7, then restart Claude |
| "Plugin not found" | Run step 4 again, then step 5 |
| `python3: command not found` or version below 3.10 | Install Python from [python.org](https://www.python.org/downloads/) (on macOS, `brew install python` also works) |
| Want to see the plugin's status | Ask Claude: *"run the markitdown-first status command"*, or run `bash scripts/run.sh status` from a clone of this repo |
| Want to update | Run `/plugin marketplace update markitdown-first`, then restart Claude |

## How it works

| When | What happens |
|---|---|
| You mention, `@`-mention, paste or drag a file path into your message | The **UserPromptSubmit** hook converts it before Claude starts and tells Claude which `.md` to read. This is how `.docx/.xlsx/.pptx` work, since Claude Code refuses to Read binary files. |
| Claude calls `Read` on a PDF, HTML, notebook… | The **PreToolUse** hook converts the file and swaps in the `.md` path. Claude never loads the original. |
| Claude finds a binary document on its own | A one-line session note tells it to run the convert command first. |
| A conversion yields almost no text (for example a scanned PDF) | The original file is read instead, so nothing is lost. |

Converted files are cached in `.markitdown-cache/` inside your project. The cache key is path + size + mtime. The folder ignores itself in git. markitdown is installed once into the plugin's private data directory (`${CLAUDE_PLUGIN_DATA}/venv`), and your system Python is untouched.

## Install

### Claude Code (CLI, and the Code tab in the desktop app)

```text
/plugin marketplace add wrteam-vimal/markitdown-first
/plugin install markitdown-first@markitdown-first
```

Restart Claude Code. The first session installs markitdown in the background, which takes about 1–2 minutes. Until it finishes, files are read normally.

**Requirements:** Python 3.10+ on `PATH` (`python3 --version`) and `bash`. On Windows, use Git Bash.

### Claude app (claude.ai, Desktop chat, Cowork)

- **Cowork / organization plugins:** add this GitHub repo as a plugin source in claude.ai settings. The plugin has no `bin/` directory, so claude.ai accepts it.
- **Chat with file uploads:** hooks don't run there, so upload the skill instead. Run `./build/build-skill-zip.sh`, then upload `dist/markitdown-first-skill.zip` in **Settings → Capabilities → Skills**. Claude will convert uploaded documents with markitdown in its code sandbox before answering.
- **Claude Desktop with local files (MCP):** add this to `claude_desktop_config.json`:

  ```json
  { "mcpServers": { "markitdown": { "command": "bash", "args": ["/path/to/markitdown-first/scripts/run.sh", "mcp"] } } }
  ```

  This exposes markitdown's `convert_to_markdown` tool. Claude Code also gets it automatically from the plugin's `.mcp.json`.

## Choose what gets converted

```text
/markitdown-first:config
```

This opens multi-select pickers (Documents / Data / Other) where you tick the types to convert, then choose **all projects** or **this project only**. You can also pass arguments:

```text
/markitdown-first:config show
/markitdown-first:config only pdf docx excel           # convert exactly these
/markitdown-first:config include pptx,html             # add types
/markitdown-first:config exclude excel                 # stop converting Excel
/markitdown-first:config exclude-path "docs/scans/**"  # never convert matching files
/markitdown-first:config off                           # pause everything
/markitdown-first:config only pdf --project            # per-project override
```

| Type key | Files | Default |
|---|---|---|
| `pdf` | .pdf | on |
| `docx` | .docx | on |
| `pptx` | .pptx | on |
| `epub` | .epub | on |
| `excel` | .xlsx .xls | on |
| `ipynb` | .ipynb | on |
| `html` | .html .htm | on |
| `msg` | .msg | on |
| `csv` | .csv | off (already text) |
| `zip` | .zip | off |
| `audio` | .mp3 .wav .m4a | off (speech transcription, slow) |
| `images` | .jpg .png … | off (Claude sees images natively; markitdown alone extracts only EXIF unless you enable an OCR plugin) |

To pick individual files to convert, run `/markitdown-first:convert [folder]`. It lists the documents and lets you multi-select which ones to convert.

### Settings files

User settings live in `~/.config/markitdown-first/config.json`. Project settings live in `.claude/markitdown-first.json` and override user settings key by key.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Master switch |
| `types` | see table | Types converted automatically |
| `exclude_paths` | `[]` | Globs matched against the file name, the project-relative path and the absolute path |
| `min_chars` | `80` | Fewer extracted characters than this → read the original |
| `max_file_mb` | `100` | Larger files are read as-is |
| `timeout_sec` | `90` | Per-file conversion timeout |
| `use_plugins` | `false` | Enable markitdown plugins, such as [markitdown-ocr](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-ocr) |
| `install` | `["markitdown[pdf,docx,pptx,xlsx,xls,outlook,audio-transcription]"]` | pip requirements for the private venv. Point it at a fork, for example `"markitdown[all] @ git+https://github.com/you/markitdown.git#subdirectory=packages/markitdown"`. The venv is rebuilt when this changes. |

## Develop

```bash
claude --plugin-dir .                 # load the plugin from this checkout
claude plugin validate --strict .     # check manifests
python3 -m unittest discover tests    # unit tests (no markitdown needed)
bash scripts/run.sh status            # inspect install + config
bash scripts/run.sh convert file.pdf  # convert by hand
```

Layout:

```text
.claude-plugin/plugin.json       plugin manifest
.claude-plugin/marketplace.json  makes this repo installable with /plugin marketplace add
hooks/hooks.json                 SessionStart, UserPromptSubmit, PreToolUse(Read)
.mcp.json                        markitdown MCP server
skills/config                    /markitdown-first:config (type picker)
skills/convert                   /markitdown-first:convert (file picker)
skills/read-documents            model-invoked guidance; also the claude.ai upload skill
scripts/mdfirst.py               all logic, stdlib-only
scripts/run.sh                   finds Python 3.10+
```

## Limits

- Images pasted straight into the chat reach Claude as images, not as files, so no hook sees them.
- Claude Code refuses to `Read` binary Office files before any hook runs. They are converted when they appear in your message, or when Claude runs the convert command, not on a bare `Read`.
- Conversion quality is markitdown's. For layout-heavy or scanned documents, exclude them or enable an OCR plugin.

## License

MIT. markitdown is © Microsoft Corporation, MIT-licensed.
