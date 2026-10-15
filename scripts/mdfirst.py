#!/usr/bin/env python3
"""markitdown-first: convert documents to Markdown before Claude reads them.

Stdlib only. Runs under any Python 3.8+; the conversion itself happens in a
private virtualenv (Python 3.10+) that holds Microsoft's `markitdown` package.

Subcommands:
  hook-pretooluse      PreToolUse hook for the Read tool (reads JSON on stdin)
  setup [--quiet]      create/refresh the private markitdown virtualenv
  status               show install state and the effective config
  types                list every file type the plugin knows about
  config ...           show / include / exclude / set / reset (see --help)
  scan [DIR]           list convertible files under DIR
  convert FILE...      convert files now and print where the Markdown went
  mcp                  run the markitdown MCP server (installs it if needed)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PLUGIN = "markitdown-first"

# File-type catalog. Keys are the names users pick from; "default" is whether a
# fresh install converts them. Images are off by default: without OCR or an LLM
# captioner markitdown only extracts EXIF metadata, and Claude reads images
# natively, so converting would lose information.
TYPES = {
    "pdf": {"label": "PDF", "ext": [".pdf"], "default": True, "group": "documents"},
    "docx": {"label": "Word", "ext": [".docx"], "default": True, "group": "documents"},
    "pptx": {"label": "PowerPoint", "ext": [".pptx"], "default": True, "group": "documents"},
    "epub": {"label": "EPUB", "ext": [".epub"], "default": True, "group": "documents"},
    "excel": {"label": "Excel", "ext": [".xlsx", ".xls"], "default": True, "group": "data"},
    "csv": {"label": "CSV", "ext": [".csv"], "default": False, "group": "data"},
    "ipynb": {"label": "Jupyter notebook", "ext": [".ipynb"], "default": True, "group": "data"},
    "zip": {"label": "ZIP archive", "ext": [".zip"], "default": False, "group": "data"},
    "html": {"label": "HTML", "ext": [".html", ".htm"], "default": True, "group": "web"},
    "msg": {"label": "Outlook email", "ext": [".msg"], "default": True, "group": "web"},
    "audio": {"label": "Audio", "ext": [".mp3", ".wav", ".m4a"], "default": False, "group": "media"},
    "images": {
        "label": "Images (OCR/EXIF)",
        "ext": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"],
        "default": False,
        "group": "media",
    },
}

DEFAULT_CONFIG = {
    "enabled": True,
    "types": [k for k, v in TYPES.items() if v["default"]],
    # Glob patterns (matched against the path relative to the project and the
    # absolute path) that are never converted.
    "exclude_paths": [],
    # Below this many characters of Markdown the original file is read instead
    # (e.g. a scanned PDF with no text layer is better read visually).
    "min_chars": 80,
    "max_file_mb": 100,
    "timeout_sec": 90,
    "use_plugins": False,
    # What pip installs into the private virtualenv. Point this at a fork with
    # e.g. "markitdown[all] @ git+https://github.com/you/markitdown.git#subdirectory=packages/markitdown"
    "install": ["markitdown[pdf,docx,pptx,xlsx,xls,outlook,audio-transcription]"],
    # OCR through an OpenAI-compatible vision model (markitdown-ocr). Normally set
    # by the plugin's install-time questions; a value here overrides them.
    "ocr": False,
    "ocr_model": "gpt-4o-mini",
    "ocr_base_url": "",
}

OCR_PACKAGES = ["markitdown-ocr", "openai"]

CACHE_DIRNAME = ".markitdown-cache"


# --------------------------------------------------------------------------- paths


def data_dir() -> Path:
    d = os.environ.get("MARKITDOWN_FIRST_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if not d:
        d = str(Path.home() / ".local" / "share" / PLUGIN)
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_dir(cwd: str | None = None) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()).resolve()


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / PLUGIN / "config.json"


def project_config_path(proj: Path) -> Path:
    return proj / ".claude" / f"{PLUGIN}.json"


def venv_dir() -> Path:
    return data_dir() / "venv"


def venv_python() -> Path:
    v = venv_dir()
    win = v / "Scripts" / "python.exe"
    return win if win.exists() else v / "bin" / "python"


def ready_marker() -> Path:
    return data_dir() / "ready.json"


# --------------------------------------------------------------------------- config


def _read_json(p: Path) -> dict:
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def ocr_state_path() -> Path:
    return data_dir() / "ocr_state.json"


def _plugin_options() -> dict:
    """OCR answers from the plugin's install-time questions. Claude Code exports
    them only to hook processes, so the non-secret ones are saved for commands
    Claude runs itself (the API key is never written to disk)."""
    env = os.environ
    opts = {}
    if env.get("CLAUDE_PLUGIN_OPTION_ENABLE_OCR", "") != "":
        opts["ocr"] = env["CLAUDE_PLUGIN_OPTION_ENABLE_OCR"].strip().lower() in ("1", "true", "yes", "on")
    for key in ("ocr_model", "ocr_base_url"):
        val = env.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").strip()
        if val:
            opts[key] = val
    return opts


def load_config(proj: Path) -> dict:
    """Defaults <- OCR install answers <- user config <- project config."""
    cfg = dict(DEFAULT_CONFIG)
    options = _plugin_options()
    cfg.update(options or _read_json(ocr_state_path()))
    cfg.update(_read_json(user_config_path()))
    cfg.update(_read_json(project_config_path(proj)))
    cfg["types"] = [t for t in cfg.get("types", []) if t in TYPES]
    if cfg.get("ocr"):
        cfg["install"] = list(cfg["install"]) + [p for p in OCR_PACKAGES if p not in cfg["install"]]
    return cfg


def ocr_api_key() -> str:
    env = os.environ
    return (
        env.get("CLAUDE_PLUGIN_OPTION_OCR_API_KEY")
        or env.get("MARKITDOWN_OCR_API_KEY")
        or env.get("OPENAI_API_KEY")
        or ""
    )


def ocr_ready(cfg: dict) -> tuple[bool, str]:
    """Whether OCR can run for this conversion, and why not."""
    if not cfg.get("ocr"):
        return False, "off"
    if not ocr_api_key() and not cfg.get("ocr_base_url"):
        return False, "no API key (set MARKITDOWN_OCR_API_KEY, or re-enter it in the plugin's settings)"
    return True, "on"


def enabled_extensions(cfg: dict) -> set[str]:
    exts: set[str] = set()
    for t in cfg["types"]:
        exts.update(TYPES[t]["ext"])
    return exts


# --------------------------------------------------------------------------- install


def is_ready(cfg: dict | None = None) -> bool:
    if not venv_python().exists():
        return False
    marker = _read_json(ready_marker())
    if cfg is not None and marker.get("install") != cfg["install"]:
        return False
    return bool(marker)


def setup(cfg: dict, quiet: bool = False, extra: list[str] | None = None) -> bool:
    """Create the virtualenv and pip-install markitdown. Idempotent."""
    if sys.version_info < (3, 10):
        _err("markitdown needs Python 3.10+; found %s. Install a newer Python." % sys.version.split()[0])
        return False
    lock = data_dir() / "install.lock"
    # Another session is installing: wait for it rather than racing pip.
    for _ in range(600):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime > 900:  # stale lock
                lock.unlink(missing_ok=True)
            time.sleep(1)
    else:
        return False
    try:
        packages = list(cfg["install"]) + list(extra or [])
        marker = _read_json(ready_marker())
        have = set(marker.get("packages", []))
        if venv_python().exists() and marker.get("install") == cfg["install"] and set(packages) <= have:
            return True
        out = subprocess.DEVNULL if quiet else sys.stderr
        if not venv_python().exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir())], check=True, stdout=out, stderr=out)
        subprocess.run(
            [str(venv_python()), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-U", *packages],
            check=True,
            stdout=out,
            stderr=out,
        )
        _write_json(
            ready_marker(),
            {"install": cfg["install"], "packages": sorted(have | set(packages)), "at": int(time.time())},
        )
        return True
    except (subprocess.CalledProcessError, OSError) as e:
        _err(f"setup failed: {e}")
        return False
    finally:
        lock.unlink(missing_ok=True)


# --------------------------------------------------------------------------- conversion


def is_excluded(path: Path, proj: Path, cfg: dict) -> bool:
    try:
        rel = path.relative_to(proj).as_posix()
    except ValueError:
        rel = None
    for pat in cfg.get("exclude_paths", []):
        if (
            fnmatch.fnmatch(path.as_posix(), pat)
            or fnmatch.fnmatch(path.name, pat)
            or (rel is not None and fnmatch.fnmatch(rel, pat))
        ):
            return True
    # Never convert our own output.
    return CACHE_DIRNAME in path.parts


def cache_path(src: Path, proj: Path, ocr_tag: str = "") -> Path:
    st = src.stat()
    key = f"{src}|{st.st_size}|{st.st_mtime_ns}|{ocr_tag}".encode()
    digest = hashlib.sha256(key).hexdigest()[:10]
    cache = proj / CACHE_DIRNAME
    if not cache.exists():
        cache.mkdir(parents=True, exist_ok=True)
        # Keep converted files out of git without touching the user's .gitignore.
        (cache / ".gitignore").write_text("*\n", encoding="utf-8")
    return cache / f"{src.name}.{digest}.md"


def convert(src: Path, proj: Path, cfg: dict) -> tuple[Path | None, str]:
    """Return (markdown_path, reason). markdown_path is None when the original
    file should be read instead."""
    if src.suffix.lower() not in enabled_extensions(cfg):
        return None, "type not enabled"
    if is_excluded(src, proj, cfg):
        return None, "path excluded"
    if not src.is_file():
        return None, "not a file"
    if src.stat().st_size > cfg["max_file_mb"] * 1024 * 1024:
        return None, f"larger than {cfg['max_file_mb']} MB"
    if not is_ready(cfg):
        return None, "markitdown not installed yet"

    use_ocr, _ = ocr_ready(cfg)
    out = cache_path(src, proj, f"ocr:{cfg['ocr_model']}" if use_ocr else "")
    if out.exists():
        return out, "cached"
    # -I: isolated mode, so a project folder named "markitdown" can't shadow the package.
    cmd = [str(venv_python()), "-I", str(Path(__file__).resolve().parent / "convert_runner.py"), str(src), str(out)]
    env = dict(os.environ, MDF_PLUGINS="1" if cfg.get("use_plugins") else "0", MDF_OCR="0")
    timeout = cfg["timeout_sec"]
    if use_ocr:
        env.update(
            MDF_OCR="1",
            MDF_OCR_MODEL=cfg["ocr_model"],
            MDF_OCR_BASE_URL=cfg.get("ocr_base_url") or "",
            MDF_OCR_API_KEY=ocr_api_key(),
        )
        timeout = max(timeout, 240)  # one model call per page image
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        out.unlink(missing_ok=True)
        return None, "conversion timed out"
    if r.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        tail = (r.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        return None, f"conversion failed: {tail[0][:200]}"
    text = out.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < cfg["min_chars"]:
        out.unlink(missing_ok=True)
        return None, "almost no text extracted (scanned/visual file?)"
    return out, "converted"


# --------------------------------------------------------------------------- hook


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def hook_pretooluse() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Read":
        return 0
    tool_input = event.get("tool_input") or {}
    raw = tool_input.get("file_path")
    if not raw:
        return 0
    proj = project_dir(event.get("cwd"))
    cfg = load_config(proj)
    if not cfg.get("enabled", True):
        return 0
    src = Path(raw).expanduser()
    if not src.is_absolute():
        src = (Path(event.get("cwd") or proj) / src)
    src = src.resolve()
    if src.suffix.lower() not in enabled_extensions(cfg):
        return 0  # fast path: not ours, stay silent

    md, reason = convert(src, proj, cfg)
    if md is None:
        if reason == "markitdown not installed yet":
            _emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": f"[{PLUGIN}] markitdown is still installing; "
                        f"{src.name} was read directly this time.",
                    }
                }
            )
        return 0  # let the original Read go through untouched

    new_input = {k: v for k, v in tool_input.items() if k != "pages"}
    new_input["file_path"] = str(md)
    note = (
        f"[{PLUGIN}] {src.name} was converted to Markdown with markitdown and "
        f"{md} was read instead of the original. If the user needs visual details "
        f"(charts, layout, images), read the original with the Read tool after running "
        f"/{PLUGIN}:config exclude-path '{src.name}', or ask the user."
    )
    # The converted copy always lands in the project's cache. For a source inside
    # the project, reading it needs no prompt. For one outside, keep the user in the
    # loop exactly as a normal Read of that file would.
    decision = "allow" if _inside(src, proj) else "ask"
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": f"{PLUGIN}: reading Markdown conversion of {src.name}",
                "updatedInput": new_input,
                "additionalContext": note,
            }
        }
    )
    return 0


_TOKEN = re.compile(r"\"[^\"]+\"|'[^']+'|(?:\\ |\S)+")


def _paths_in_prompt(prompt: str, base: Path, exts: set[str]) -> list[Path]:
    """Find existing files with a convertible extension mentioned in a prompt:
    plain or quoted paths, @mentions, terminal drag-and-drop (`a\\ b.pdf`) and
    file:// URIs."""
    found: list[Path] = []
    for tok in _TOKEN.findall(prompt):
        t = tok.strip("\"'").lstrip("@").rstrip(".,;:!?)]}>")
        t = t.replace("\\ ", " ")
        if t.startswith("file://"):
            t = t[len("file://"):]
        if Path(t).suffix.lower() not in exts:
            continue
        p = Path(t).expanduser()
        if not p.is_absolute():
            p = base / p
        try:
            p = p.resolve()
        except OSError:
            continue
        if p.is_file() and p not in found:
            found.append(p)
        if len(found) >= 20:
            break
    return found


def hook_userpromptsubmit() -> int:
    """Convert files named in the user's message before Claude starts working.

    This is what makes binary formats (docx, xlsx, pptx…) work: Claude Code
    rejects a Read of those before PreToolUse hooks run, so they have to be
    converted up front and Claude pointed at the Markdown copy."""
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    prompt = event.get("prompt") or ""
    proj = project_dir(event.get("cwd"))
    cfg = load_config(proj)
    if not cfg.get("enabled", True):
        return 0
    files = _paths_in_prompt(prompt, Path(event.get("cwd") or proj), enabled_extensions(cfg))
    if not files:
        return 0
    lines = []
    for src in files:
        md, reason = convert(src, proj, cfg)
        if md:
            lines.append(f"- {src} -> {md} ({_kb(src.stat().st_size)} -> {_kb(md.stat().st_size)})")
        elif reason == "markitdown not installed yet":
            lines.append(f"- {src}: not converted, markitdown is still installing")
    if not lines:
        return 0
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"[{PLUGIN}] Files in this message were converted to Markdown. "
                "Read the .md path instead of the original unless visual details are needed:\n"
                + "\n".join(lines),
            }
        }
    )
    return 0


def hook_sessionstart() -> int:
    root = Path(__file__).resolve().parent
    options = _plugin_options()
    if options:  # remember the non-secret OCR answers for /markitdown-first:convert
        _write_json(ocr_state_path(), options)
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"[{PLUGIN}] To read .docx/.xlsx/.xls/.pptx/.epub/.msg files (which the Read tool "
                f"rejects as binary), first run: bash \"{root / 'run.sh'}\" convert <file> — then Read the printed .md path.",
            }
        }
    )
    return 0


def _inside(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- CLI


def _err(msg: str) -> None:
    print(f"{PLUGIN}: {msg}", file=sys.stderr)


def cmd_status(proj: Path) -> int:
    cfg = load_config(proj)
    marker = _read_json(ready_marker())
    print(f"enabled:        {cfg['enabled']}")
    print(f"installed:      {'yes' if is_ready(cfg) else 'no (run setup)'}")
    if marker:
        print(f"packages:       {', '.join(marker.get('packages', []))}")
    print(f"converting:     {', '.join(cfg['types']) or '(nothing)'}")
    off = [t for t in TYPES if t not in cfg["types"]]
    print(f"not converting: {', '.join(off) or '(nothing)'}")
    print(f"exclude_paths:  {cfg['exclude_paths'] or '(none)'}")
    use_ocr, why = ocr_ready(cfg)
    if cfg.get("ocr"):
        where = cfg.get("ocr_base_url") or "OpenAI"
        print(f"ocr:            {'on' if use_ocr else 'NOT ACTIVE: ' + why} (model {cfg['ocr_model']} via {where})")
    else:
        print("ocr:            off")
    print(f"min_chars={cfg['min_chars']} max_file_mb={cfg['max_file_mb']} timeout_sec={cfg['timeout_sec']} use_plugins={cfg['use_plugins']}")
    print(f"user config:    {user_config_path()}")
    print(f"project config: {project_config_path(proj)}")
    print(f"cache:          {proj / CACHE_DIRNAME}")
    return 0


def cmd_types() -> int:
    for k, v in TYPES.items():
        print(f"{k:8} {v['group']:9} {'on ' if v['default'] else 'off'}  {v['label']:20} {' '.join(v['ext'])}")
    return 0


def _kb(n: int) -> str:
    return f"{n / 1024:.1f}KB"


def _parse_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return out


def _resolve_type(name: str) -> str | None:
    n = name.lower().lstrip(".")
    if n in TYPES:
        return n
    for k, v in TYPES.items():
        if "." + n in v["ext"]:
            return k
    if n in ("all", "*"):
        return "*"
    return None


def cmd_config(args, proj: Path) -> int:
    path = project_config_path(proj) if args.project else user_config_path()
    stored = _read_json(path)
    effective = load_config(proj)
    if args.action == "show":
        return cmd_status(proj)
    if args.action == "reset":
        if path.exists():
            path.unlink()
        print(f"reset {path}")
        return 0

    values = _parse_list(args.values)
    if args.action in ("include", "exclude", "only"):
        resolved = []
        for v in values:
            r = _resolve_type(v)
            if r is None:
                _err(f"unknown type '{v}'. Known: {', '.join(TYPES)}")
                return 2
            resolved.extend(TYPES if r == "*" else [r])
        current = list(stored.get("types", effective["types"]))
        if args.action == "only":
            current = resolved
        elif args.action == "include":
            current += [r for r in resolved if r not in current]
        else:
            current = [t for t in current if t not in resolved]
        stored["types"] = [t for t in TYPES if t in current]  # stable order
    elif args.action in ("exclude-path", "include-path"):
        pats = list(stored.get("exclude_paths", effective["exclude_paths"]))
        if args.action == "exclude-path":
            pats += [v for v in values if v not in pats]
        else:
            pats = [p for p in pats if p not in values]
        stored["exclude_paths"] = pats
    elif args.action in ("on", "off"):
        stored["enabled"] = args.action == "on"
    elif args.action == "set":
        for v in values:
            key, _, val = v.partition("=")
            if key not in DEFAULT_CONFIG or key == "types":
                _err(f"unknown key '{key}'")
                return 2
            default = DEFAULT_CONFIG[key]
            if isinstance(default, bool):
                stored[key] = val.lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                stored[key] = int(val)
            elif isinstance(default, list):
                stored[key] = [x for x in val.split(";") if x]
            else:
                stored[key] = val
    _write_json(path, stored)
    print(f"saved {path}")
    return cmd_status(proj)


def cmd_scan(root: Path, proj: Path) -> int:
    cfg = load_config(proj)
    exts = {e for v in TYPES.values() for e in v["ext"]}
    on = enabled_extensions(cfg)
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in exts:
                state = "auto" if p.suffix.lower() in on and not is_excluded(p.resolve(), proj, cfg) else "skip"
                rows.append((state, p.stat().st_size, p))
        if len(rows) > 500:
            break
    for state, size, p in sorted(rows, key=lambda r: str(r[2])):
        print(f"{state}\t{_kb(size)}\t{p}")
    if not rows:
        print("(no convertible files found)")
    return 0


def cmd_convert(files: list[str], proj: Path, force: bool) -> int:
    cfg = load_config(proj)
    if not is_ready(cfg) and not setup(cfg, quiet=True):
        return 1
    if force:  # manual conversion ignores the type/path filters
        cfg = dict(cfg, types=list(TYPES), exclude_paths=[], min_chars=1)
    rc = 0
    for f in files:
        src = Path(f).expanduser().resolve()
        md, reason = convert(src, proj, cfg)
        if md:
            size_in, size_out = src.stat().st_size, md.stat().st_size
            print(f"OK\t{src}\t->\t{md}\t({_kb(size_in)} -> {_kb(size_out)}, {reason})")
        else:
            print(f"SKIP\t{src}\t{reason}")
            rc = 1
    return rc


def cmd_mcp(proj: Path) -> int:
    cfg = load_config(proj)
    if not setup(cfg, quiet=True, extra=["markitdown-mcp"]):
        return 1
    v = venv_dir()
    exe = v / "Scripts" / "markitdown-mcp.exe"
    if not exe.exists():
        exe = v / "bin" / "markitdown-mcp"
    os.execv(str(exe), [str(exe)])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=PLUGIN, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook-pretooluse")
    sub.add_parser("hook-userpromptsubmit")
    sub.add_parser("hook-sessionstart")
    s = sub.add_parser("setup")
    s.add_argument("--quiet", action="store_true")
    sub.add_parser("status")
    sub.add_parser("types")
    c = sub.add_parser("config")
    c.add_argument(
        "action",
        choices=["show", "include", "exclude", "only", "exclude-path", "include-path", "on", "off", "set", "reset"],
    )
    c.add_argument("values", nargs="*")
    c.add_argument("--project", action="store_true", help="write to this project's config instead of the user config")
    sc = sub.add_parser("scan")
    sc.add_argument("dir", nargs="?", default=".")
    cv = sub.add_parser("convert")
    cv.add_argument("files", nargs="+")
    cv.add_argument("--force", action="store_true", help="convert even if the type/path is excluded")
    sub.add_parser("mcp")
    args = ap.parse_args(argv)

    proj = project_dir()
    hooks = {
        "hook-pretooluse": hook_pretooluse,
        "hook-userpromptsubmit": hook_userpromptsubmit,
        "hook-sessionstart": hook_sessionstart,
    }
    if args.cmd in hooks:
        try:
            return hooks[args.cmd]()
        except Exception as e:  # a broken hook must never block Claude
            _err(f"hook error: {e}")
            return 0
    if args.cmd == "setup":
        return 0 if setup(load_config(proj), quiet=args.quiet) else 1
    if args.cmd == "status":
        return cmd_status(proj)
    if args.cmd == "types":
        return cmd_types()
    if args.cmd == "config":
        return cmd_config(args, proj)
    if args.cmd == "scan":
        return cmd_scan(Path(args.dir).resolve(), proj)
    if args.cmd == "convert":
        return cmd_convert(args.files, proj, args.force)
    if args.cmd == "mcp":
        return cmd_mcp(proj)
    return 2


if __name__ == "__main__":
    sys.exit(main())
