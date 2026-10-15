#!/usr/bin/env bash
# Run scripts/mdfirst.py with the newest Python 3 available.
# markitdown needs 3.10+, so minor-versioned binaries are tried first; the
# Windows Store "python3" stub fails the probe and is skipped.
export PYTHONUTF8=1
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/mdfirst.py"
if command -v cygpath >/dev/null 2>&1; then script="$(cygpath -w "$script")"; fi

if [ -n "$MARKITDOWN_FIRST_PYTHON" ]; then exec "$MARKITDOWN_FIRST_PYTHON" "$script" "$@"; fi

for cmd in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python "py -3"; do
  # shellcheck disable=SC2086
  v=$($cmd -c 'import sys; print(sys.version_info >= (3, 10))' 2>/dev/null) || continue
  if [ "$v" = "True" ]; then
    # shellcheck disable=SC2086
    exec $cmd "$script" "$@"
  fi
done

# Fall back to any Python 3: the hook and config commands still work and will
# report that conversion needs Python 3.10+.
for cmd in python3 python "py -3"; do
  # shellcheck disable=SC2086
  $cmd -c '' 2>/dev/null && exec $cmd "$script" "$@"
done

echo "markitdown-first: no Python 3 found. Install Python 3.10+ from https://python.org" >&2
exit 0
