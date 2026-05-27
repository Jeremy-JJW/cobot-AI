"""将 Markdown 转为 PDF（汇报用）。用法: python scripts/md_to_pdf.py [输入.md] [输出.pdf]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #1a1a1a;
}
h1 { font-size: 20pt; border-bottom: 2px solid #2563eb; padding-bottom: 0.3em; margin-top: 0; }
h2 { font-size: 15pt; color: #1e40af; margin-top: 1.4em; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 1.1em; page-break-after: avoid; }
blockquote {
  margin: 0.8em 0; padding: 0.6em 1em;
  border-left: 4px solid #2563eb; background: #f0f7ff; color: #334155;
}
table {
  width: 100%; border-collapse: collapse; margin: 0.8em 0;
  font-size: 10pt;
}
tr { page-break-inside: avoid; }
th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #eff6ff; font-weight: 600; }
code, pre { font-family: Consolas, "Courier New", monospace; font-size: 9pt; }
pre {
  background: #f8fafc; border: 1px solid #e2e8f0;
  padding: 10px 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-all;
}
hr { border: none; border-top: 1px solid #e2e8f0; margin: 1.5em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: 0.25em 0; }
"""

COMPACT_CSS = """
@page { size: A4; margin: 10mm 12mm; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  font-size: 8.5pt;
  line-height: 1.35;
  color: #1a1a1a;
}
h1 { font-size: 14pt; border-bottom: 2px solid #2563eb; padding-bottom: 0.2em; margin: 0 0 0.4em; }
h2 { font-size: 10pt; color: #1e40af; margin: 0.55em 0 0.25em; page-break-after: avoid; }
blockquote { margin: 0.3em 0; padding: 0.3em 0.6em; font-size: 8pt; border-left: 3px solid #2563eb; background: #f0f7ff; }
table { width: 100%; border-collapse: collapse; margin: 0.25em 0; font-size: 7.8pt; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #cbd5e1; padding: 3px 5px; text-align: left; vertical-align: top; }
th { background: #eff6ff; font-weight: 600; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 0.4em 0; }
"""


def md_to_html(md_text: str, *, compact: bool = False) -> str:
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )
    css = COMPACT_CSS if compact else CSS
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>方案规划</title>
  <style>{css}</style>
</head>
<body>{body}</body>
</html>"""


def html_to_pdf(html: str, pdf_path: Path, *, compact: bool = False) -> None:
    margin = {"top": "10mm", "bottom": "10mm", "left": "12mm", "right": "12mm"} if compact else {
        "top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin=margin,
        )
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown → PDF")
    parser.add_argument("input", nargs="?", default=str(ROOT / "方案规划.md"))
    parser.add_argument("output", nargs="?", default=None)
    parser.add_argument("--compact", action="store_true", help="紧凑排版，适合一页速查表")
    args = parser.parse_args()

    md_path = Path(args.input).resolve()
    if not md_path.exists():
        print(f"找不到文件: {md_path}", file=sys.stderr)
        return 1

    pdf_path = Path(args.output).resolve() if args.output else md_path.with_suffix(".pdf")
    md_text = md_path.read_text(encoding="utf-8")
    html = md_to_html(md_text, compact=args.compact)
    html_to_pdf(html, pdf_path, compact=args.compact)
    print(f"已生成: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
