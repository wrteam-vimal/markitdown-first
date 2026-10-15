---
name: convert
description: Convert chosen files (PDF, Word, PowerPoint, Excel, HTML, EPUB, Outlook, audio…) to Markdown with markitdown. Pick files from a list or pass paths. Use when the user asks to convert documents to Markdown or wants to choose which uploaded files get converted.
argument-hint: "[file-or-folder ...]"
---

# Convert files to Markdown

The helper is `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"`. Call it `MDF` below.

Arguments: `$ARGUMENTS`

1. **Find the candidates.**
   - If the arguments name files, those are the candidates.
   - If they name a folder, or nothing was given, run `MDF scan <folder or .>`. Each output line is `auto|skip <TAB> size <TAB> path`. `auto` means the hook already converts that file whenever Claude reads it.
2. **Let the user choose** when there are 2 or more candidates and they didn't say "all".
   - Up to 4 files: one AskUserQuestion question with `multiSelect: true` and one option per file (label = file name, description = size and folder).
   - 5 to 16 files: split them across up to 4 multiSelect questions of up to 4 files each, grouped by type.
   - More than 16 files: ask which **types or folders** to convert, then expand that choice into the file list.
3. Run `MDF convert --force <file> [<file> ...]` with the chosen paths. Quote each path. `--force` converts even types the user turned off for automatic conversion.
4. Each `OK` line shows the source, the `.md` path and the size change. Report a short table: file, Markdown path, size before → after. For `SKIP` lines, give the reason.
5. When the user wants to work with the content, Read the `.md` files rather than the originals.
