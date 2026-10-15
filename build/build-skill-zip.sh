#!/usr/bin/env bash
# Package skills/read-documents as an uploadable skill for claude.ai / Claude Desktop
# (Settings -> Capabilities -> Skills). Output: dist/markitdown-first-skill.zip
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/markitdown-first" "$root/dist"
# The plugin-only section refers to hooks that don't exist on claude.ai; drop it.
awk '/^## In Claude Code with this plugin enabled/{skip=1; next} /^## /{skip=0} !skip' \
  "$root/skills/read-documents/SKILL.md" \
  | sed 's/^name: read-documents$/name: markitdown-first/' > "$stage/markitdown-first/SKILL.md"
rm -f "$root/dist/markitdown-first-skill.zip"
(cd "$stage" && zip -qr "$root/dist/markitdown-first-skill.zip" markitdown-first)
echo "built dist/markitdown-first-skill.zip"
