---
name: read-documents
description: Read PDFs, Word, PowerPoint, Excel, EPUB, HTML, Outlook .msg and similar uploaded or attached files by converting them to Markdown with Microsoft markitdown first. This saves tokens and keeps tables and headings. Use whenever the user uploads, attaches or points to such a file and asks about its contents.
---

# Read documents as Markdown first

Markdown is far cheaper to read than rendered PDF pages or raw Office XML, and markitdown keeps headings, lists and tables.

## In Claude Code with this plugin enabled

A hook already does the work. When you Read a supported file, the hook converts it and you receive the `.md` copy from `.markitdown-cache/`. The context note starts with `[markitdown-first]`. You need to do nothing extra.

- If the note says markitdown is still installing, the original was read. Continue normally.
- Read the original file only when the user needs visual details the Markdown can't carry, such as charts, page layout, signatures or embedded images. To let the original through, run `/markitdown-first:config exclude-path "<name>"`.
- For several files at once, use `/markitdown-first:convert`.

## Anywhere else (claude.ai, Claude desktop, sandboxes without the hook)

If you can run code (for example uploads under `/mnt/user-data/uploads`):

```bash
pip install -q 'markitdown[pdf,docx,pptx,xlsx,xls,outlook]' 2>/dev/null || pip install -q --break-system-packages 'markitdown[pdf,docx,pptx,xlsx,xls,outlook]'
mkdir -p /tmp/md && for f in /mnt/user-data/uploads/*; do
  case "${f,,}" in *.pdf|*.docx|*.pptx|*.xlsx|*.xls|*.epub|*.html|*.htm|*.msg|*.ipynb)
    markitdown "$f" -o "/tmp/md/$(basename "$f").md" && echo "OK $f";;
  esac
done
```

Then answer from the files in `/tmp/md/`. If a file yields almost no text, it is likely scanned. Fall back to the original and say so.

If the `markitdown` MCP tool `convert_to_markdown` is available, call it with a `file:///absolute/path` URI.
