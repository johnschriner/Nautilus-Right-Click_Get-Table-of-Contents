# GetMagazineTOC — Magazine Table-of-Contents Extractor (WIP)

A fast, local, right-click tool that extracts a clean, Calibre-friendly table of contents from magazine PDFs. It targets The New Yorker, The Atlantic, and Harper’s Magazine first—but is designed to be extensible to other periodicals.

Status: work in progress. Harper’s support is improving; New Yorker and Atlantic are solid for most issues. OCR + robust parsing paths are included.

-------------------------------------------------------------------------------

## What it does

- Auto-detects brand from filename/early pages (NYer / Atlantic / Harper’s); defaults to “auto.”
- Extracts ToC from the first N pages using pdftotext (-layout, with -raw fallback).
- OCR fallback for image-only or sparse PDFs (first N pages via pdftoppm + tesseract).
- Brand-specific parsing:
  - The New Yorker: section headings (e.g., PERSONAL HISTORY, THE CRITICS), titles, authors, pages.
  - The Atlantic: sections + features with page numbers.
  - Harper’s: section headers like “LETTERS    2”, plus multiple item patterns; avoids Harper’s Index/Findings bleed-through.
- Nice plain-text output (non-markdown) designed to paste into Calibre notes/Comments.
- Verbose mode to see exactly what’s happening (commands run, sections detected, fallbacks).

-------------------------------------------------------------------------------

## Requirements

System packages (Ubuntu/Debian):
  sudo apt install -y poppler-utils tesseract-ocr tesseract-ocr-eng zenity libnotify-bin

Python:
- Works with the system Python 3.10+ (tested on 3.12).
- No third-party pip deps required.

Recommended venv:
  python3 -m venv ~/.venvs/nautilus-pdf
  ~/.venvs/nautilus-pdf/bin/python -m pip install --upgrade pip

-------------------------------------------------------------------------------

## Installation (Nautilus right-click)

1) Create folders:
  mkdir -p ~/.local/share/nautilus/scripts
  mkdir -p ~/.local/share/nautilus/scripts-support

2) Copy files:
  GetMagazineTOC  -> ~/.local/share/nautilus/scripts/
  get_mag_toc.py  -> ~/.local/share/nautilus/scripts-support/

3) Make executable:
  chmod +x ~/.local/share/nautilus/scripts/GetMagazineTOC
  chmod +x ~/.local/share/nautilus/scripts-support/get_mag_toc.py

4) (Optional) set the Python path inside the launcher:
  # inside GetMagazineTOC
  : "${PYBIN:=~/.venvs/nautilus-pdf/bin/python}"

5) Restart Nautilus:
  nautilus -q

Now right-click any PDF → Scripts → GetMagazineTOC.

-------------------------------------------------------------------------------

## CLI usage

Run the core script directly (handy for debugging):

  PDF="~/Downloads/The New Yorker - November 10, 2025.pdf"
  ~/.venvs/nautilus-pdf/bin/python ~/.local/share/nautilus/scripts-support/get_mag_toc.py \
    "$PDF" --pages 16 --ocr-first 3 --brand auto --verbose

Key flags:
- --pages N               scan the first N pages (default 16)
- --ocr-first N           OCR first N pages if text seems sparse (default 3)
- --brand {auto,newyorker,atlantic,harpers}
- --include-mail          include THE MAIL items
- --include-contributors  include CONTRIBUTORS items
- --no-suppress-empty     show section headings even if no items were parsed
- --json                  emit JSON instead of plain text (for scripting)
- --out PATH              write output to a file (otherwise prints to stdout)

-------------------------------------------------------------------------------

## Output (example, plain text)

GOINGS ON (p. 4)
THE TALK OF THE TOWN (p. 15)

PERSONAL HISTORY (p. 20)
• Transitions (p. 20) — James Marcus

TAKES (p. 25)
• Nick Paumgarten’s “Up and Then Down.” (p. 25) — Ed Caesar

(Exact details depend on the issue and detected patterns.)

-------------------------------------------------------------------------------

## Troubleshooting

- “Silent” right-click: check the log at ~/.cache/get_mag_toc.log
- Sparse/garbled text: try increasing --ocr-first or --pages
- Harper’s only shows one line: some lines are split across wraps; see roadmap (two-line joiner)
- Missing binaries: ensure pdftotext, pdftoppm, and tesseract are installed and on PATH
- Brand mis-detected: pass --brand harpers|newyorker|atlantic explicitly to compare behavior

-------------------------------------------------------------------------------

## Roadmap

- Harper’s two-line joiner: fuse title-only line + following page-number line before matching
- Block-scoped parsing: collect lines under each section and match with multiple tolerant patterns
- Brand auto-detect++: prefer filename → page-1 text → OCR page-1 text
- Generic mode for other periodicals with learnable patterns
- Unit test fixtures per brand/issue to prevent regressions
- Structured exports: CSV/JSON with (section, title, author, page)

-------------------------------------------------------------------------------

