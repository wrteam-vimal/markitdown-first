"""Convert one file to Markdown. Runs inside the plugin's private virtualenv.

usage: python -I convert_runner.py SRC OUT

Environment (set by mdfirst.py):
  MDF_PLUGINS=1        enable markitdown plugins (e.g. markitdown-ocr)
  MDF_OCR=1            use an OpenAI-compatible vision model for OCR / image text
  MDF_OCR_MODEL        model name, e.g. gpt-4o-mini
  MDF_OCR_BASE_URL     optional endpoint, e.g. http://localhost:11434/v1 for Ollama
  MDF_OCR_API_KEY      API key (optional for local endpoints)
"""

import os
import sys

from markitdown import MarkItDown


def main() -> int:
    src, out = sys.argv[1], sys.argv[2]
    kwargs = {}
    plugins = os.environ.get("MDF_PLUGINS") == "1"
    if os.environ.get("MDF_OCR") == "1":
        from openai import OpenAI

        kwargs["llm_client"] = OpenAI(
            api_key=os.environ.get("MDF_OCR_API_KEY") or "not-needed",
            base_url=os.environ.get("MDF_OCR_BASE_URL") or None,
        )
        kwargs["llm_model"] = os.environ["MDF_OCR_MODEL"]
        plugins = True  # markitdown-ocr is a markitdown plugin
    result = MarkItDown(enable_plugins=plugins, **kwargs).convert(src)
    with open(out, "w", encoding="utf-8") as f:
        f.write(result.markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
