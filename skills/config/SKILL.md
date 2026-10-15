---
name: config
description: Choose which file types markitdown-first converts to Markdown before Claude reads them (multi-select), exclude paths, or turn auto-conversion on/off.
argument-hint: "[show | include <types> | exclude <types> | only <types> | exclude-path <glob> | include-path <glob> | on | off | reset] [--project]"
disable-model-invocation: true
---

# markitdown-first settings

The helper is `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"`. Call it `MDF` below.

Arguments from the user: `$ARGUMENTS`

## If arguments were given

Run `MDF config $ARGUMENTS` and report the resulting "converting" and "not converting" lines in one or two sentences. Type names: `pdf docx pptx epub excel csv ipynb zip html msg audio images` (or `all`). Extensions such as `xlsx` or `.png` also work.

## If no arguments were given: interactive picker

1. Run `MDF status` to read the current settings.
2. Ask with **one AskUserQuestion call** containing these four questions. Use `multiSelect: true` for the first three. In each option label, add " (on)" if that type is currently in the "converting" list.
   - **Documents** (header "Documents"): PDF (`pdf`), Word .docx (`docx`), PowerPoint .pptx (`pptx`), EPUB (`epub`)
   - **Data** (header "Data"): Excel .xlsx/.xls (`excel`), CSV (`csv`), Jupyter .ipynb (`ipynb`), ZIP archives (`zip`)
   - **Web, mail, media** (header "Other"): HTML (`html`), Outlook .msg (`msg`), Audio mp3/wav/m4a, transcribed (`audio`), Images, OCR/EXIF only (`images`). Say in the Images description that Claude already sees images natively, so this helps only with OCR plugins.
   - **Scope** (header "Scope", single select): "All my projects (Recommended)" writes the user config. "This project only" writes `.claude/markitdown-first.json`.
3. Join every selected type key with commas and run `MDF config only <keys>`. Add `--project` if the scope is "This project only". If nothing was selected, run `MDF config off` instead, and say that auto-conversion is now off.
4. Report in one or two sentences: which types are converted, which are read as-is, and where the setting was saved.

## Notes to pass on only if the user asks

- `exclude-path "<glob>"` skips matching files, for example `"docs/scans/**"` or `"*.signed.pdf"`. `include-path` removes such a pattern.
- `MDF config set min_chars=200`: below this many extracted characters, the original file is read instead.
- `max_file_mb`, `timeout_sec` and `use_plugins=true` work the same way.
- OCR (scanned PDFs, text in images) uses a vision model and is normally set by the install questions. Override it with `MDF config set ocr=true|false`, `ocr_model=<name>` and `ocr_base_url=<url>`, adding `--project` for this project only. The `ocr:` line of `MDF status` shows whether OCR is active and, if not, why. Images are worth enabling (`include images`) only when OCR is on.
- `MDF config set "install=markitdown[all] @ git+https://github.com/<you>/markitdown.git#subdirectory=packages/markitdown"` installs from a fork. Then run `MDF setup`.
