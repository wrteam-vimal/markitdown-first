"""Unit tests that run without markitdown installed: python3 -m unittest discover tests"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mdfirst  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.proj = root / "proj"
        self.proj.mkdir()
        self.env = mock.patch.dict(
            os.environ,
            {
                "CLAUDE_PROJECT_DIR": str(self.proj),
                "MARKITDOWN_FIRST_DATA": str(root / "data"),
                "XDG_CONFIG_HOME": str(root / "cfg"),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, *argv, stdin=None):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(stdin or "")):
            rc = mdfirst.main(list(argv))
        return rc, out.getvalue()


class PromptPaths(Base):
    def test_finds_plain_quoted_at_and_escaped_paths(self):
        for name in ("a.pdf", "b.xlsx", "my deck.pptx", "c.docx", "notes.txt"):
            (self.proj / name).write_bytes(b"x")
        prompt = f'read a.pdf, @b.xlsx and {self.proj}/my\\ deck.pptx plus "c.docx". Ignore notes.txt and missing.pdf'
        exts = mdfirst.enabled_extensions(mdfirst.load_config(self.proj))
        found = [p.name for p in mdfirst._paths_in_prompt(prompt, self.proj, exts)]
        self.assertEqual(found, ["a.pdf", "b.xlsx", "my deck.pptx", "c.docx"])


class Config(Base):
    def test_defaults(self):
        cfg = mdfirst.load_config(self.proj)
        self.assertIn("pdf", cfg["types"])
        self.assertNotIn("images", cfg["types"])

    def test_include_exclude_only_by_type_or_extension(self):
        self.run_cli("config", "exclude", "xlsx,pdf")
        types = mdfirst.load_config(self.proj)["types"]
        self.assertNotIn("excel", types)
        self.assertNotIn("pdf", types)
        self.run_cli("config", "include", ".png")
        self.assertIn("images", mdfirst.load_config(self.proj)["types"])
        self.run_cli("config", "only", "pdf", "docx")
        self.assertEqual(mdfirst.load_config(self.proj)["types"], ["pdf", "docx"])

    def test_project_overrides_user(self):
        self.run_cli("config", "only", "pdf")
        self.run_cli("config", "only", "excel", "--project")
        self.assertEqual(mdfirst.load_config(self.proj)["types"], ["excel"])

    def test_unknown_type_rejected(self):
        rc, _ = self.run_cli("config", "include", "banana")
        self.assertEqual(rc, 2)

    def test_exclude_path_matches_name_and_relative_glob(self):
        self.run_cli("config", "exclude-path", "secret.pdf", "scans/**")
        cfg = mdfirst.load_config(self.proj)
        self.assertTrue(mdfirst.is_excluded(self.proj / "x" / "secret.pdf", self.proj, cfg))
        self.assertTrue(mdfirst.is_excluded(self.proj / "scans" / "a" / "b.pdf", self.proj, cfg))
        self.assertFalse(mdfirst.is_excluded(self.proj / "ok.pdf", self.proj, cfg))


class Hooks(Base):
    def event(self, path, tool="Read"):
        return json.dumps({"tool_name": tool, "cwd": str(self.proj), "tool_input": {"file_path": str(path)}})

    def test_non_document_is_silent(self):
        (self.proj / "a.py").write_text("print(1)")
        _, out = self.run_cli("hook-pretooluse", stdin=self.event(self.proj / "a.py"))
        self.assertEqual(out, "")

    def test_not_installed_passes_original_through_with_note(self):
        (self.proj / "a.pdf").write_bytes(b"%PDF")
        _, out = self.run_cli("hook-pretooluse", stdin=self.event(self.proj / "a.pdf"))
        ctx = json.loads(out)["hookSpecificOutput"]
        self.assertNotIn("updatedInput", ctx)
        self.assertIn("still installing", ctx["additionalContext"])

    def test_redirects_to_markdown_and_drops_pages(self):
        src = self.proj / "a.pdf"
        src.write_bytes(b"%PDF")
        md = self.proj / ".markitdown-cache" / "a.pdf.x.md"
        with mock.patch.object(mdfirst, "convert", return_value=(md, "converted")):
            ev = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(src), "pages": "1-3"}})
            _, out = self.run_cli("hook-pretooluse", stdin=ev)
        h = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(h["updatedInput"], {"file_path": str(md)})
        self.assertEqual(h["permissionDecision"], "allow")

    def test_file_outside_project_asks(self):
        with tempfile.TemporaryDirectory() as other:
            src = Path(other) / "a.pdf"
            src.write_bytes(b"%PDF")
            md = self.proj / ".markitdown-cache" / "a.pdf.x.md"
            with mock.patch.object(mdfirst, "convert", return_value=(md, "converted")):
                _, out = self.run_cli("hook-pretooluse", stdin=self.event(src))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_disabled_is_silent(self):
        self.run_cli("config", "off")
        (self.proj / "a.pdf").write_bytes(b"%PDF")
        _, out = self.run_cli("hook-pretooluse", stdin=self.event(self.proj / "a.pdf"))
        self.assertEqual(out, "")

    def test_bad_stdin_never_raises(self):
        rc, _ = self.run_cli("hook-userpromptsubmit", stdin="not json")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
