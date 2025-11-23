#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_mag_toc.py — Unified Table-of-Contents extractor for magazines.
Brands: The New Yorker, The Atlantic, Harper's Magazine.

Harper's-focused fixes in this build:
- Brand auto-detect (filename first)
- TOC page finder (pages 1–7; fallback to 3)
- Parse TOC page + next page, in BOTH -layout and -raw, and MERGE
- Do NOT slice region for Harper's (avoid trimming)
- Robust item patterns incl. space-only leaders and Unicode leaders
"""

import argparse, json, re, subprocess, sys, tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional, Dict

# ---------- utils ----------
def which(cmd: str) -> Optional[str]:
    import shutil as _sh
    return _sh.which(cmd)

def run_cmd(cmd, check=True, capture_output=True, text=True):
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)

def eprint(msg: str, quiet: bool = False):
    if not quiet:
        print(msg, file=sys.stderr)

# ---------- extractors ----------
def pdftotext_extract(pdf: Path, pages: int, quiet: bool, mode: str = "layout") -> str:
    if not which("pdftotext"): raise RuntimeError("pdftotext not found")
    args = ["-layout"] if mode == "layout" else ["-raw"]
    cmd = ["pdftotext", *args, "-f", "1", "-l", str(pages), str(pdf), "-"]
    eprint(f"[text] {' '.join(cmd)}", quiet)
    return run_cmd(cmd).stdout or ""

def pdftotext_extract_page(pdf: Path, page: int, quiet: bool, mode: str = "layout") -> str:
    if not which("pdftotext"): raise RuntimeError("pdftotext not found")
    args = ["-layout"] if mode == "layout" else ["-raw"]
    cmd = ["pdftotext", *args, "-f", str(page), "-l", str(page), str(pdf), "-"]
    eprint(f"[text] {' '.join(cmd)}", quiet)
    return run_cmd(cmd).stdout or ""

def ocr_first_pages(pdf: Path, n_pages: int, quiet: bool) -> str:
    if not which("pdftoppm") or not which("tesseract"): return ""
    parts = []
    with tempfile.TemporaryDirectory(prefix="toc_ocr_") as td:
        prefix = str(Path(td) / "pg")
        cmd_ppm = ["pdftoppm", "-f", "1", "-l", str(n_pages), "-r", "300", str(pdf), prefix]
        eprint(f"[ocr] {' '.join(cmd_ppm)}", quiet)
        run_cmd(cmd_ppm)
        for img in sorted(Path(td).glob("pg*.ppm")):
            base = img.with_suffix("")
            cmd_t = ["tesseract", str(img), str(base)]
            eprint(f"[ocr] {' '.join(cmd_t)}", quiet)
            try: run_cmd(cmd_t)
            except subprocess.CalledProcessError: continue
            txt = Path(f"{base}.txt")
            if txt.exists():
                parts.append(txt.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)

def looks_sparse(text: str) -> bool:
    core = re.sub(r"[\W_]+", "", text)
    return len(core) < 300

# ---------- data ----------
@dataclass
class TocItem:
    page: Optional[int]
    title: str
    section: Optional[str] = None
    author: Optional[str] = None

NY_SECTIONS = [
    "THE TALK OF THE TOWN","PERSONAL HISTORY","TAKES","SHOUTS & MURMURS",
    "ANNALS OF ARTIFICIAL INTELLIGENCE","A REPORTER AT LARGE","PROFILES","FICTION",
    "THE CRITICS","BOOKS","THE CURRENT CINEMA","THE THEATRE","POEMS","GOINGS ON",
    "COVER","CONTRIBUTORS","TABLES FOR TWO","MUSICAL EVENTS","ON AND OFF THE MENU","THE MAIL"
]
ATL_SECTIONS = [
    "FEATURES","DISPATCHES","IDEAS","CULTURE","POLITICS","SCIENCE",
    "TECHNOLOGY","BUSINESS","BOOKS","REVIEW","ESSAYS","VOICES","CORRESPONDENCE"
]
HARPERS_SECTIONS = [
    "READINGS","ESSAY","REPORT","NOTEBOOK","LETTER","LETTERS","REVIEWS","REVIEW",
    "POEM","POETRY","FICTION","ART","ARTS & LETTERS","ANNOTATIONS","DEPARTMENTS"
]

NOISE_UPPER = {
    "PRICE $","ILLUSTRATIONS BY","WINTER PREVIEW","THE WEEKEND ESSAY","SUBSCRIBE",
    "THE NEW YORKER,","LOVE BOOKS, LOVE FOLIO",
    "HARPER'S INDEX","HARPER’S INDEX","HARPERS INDEX","FINDINGS"
}

FOOTER_RE = re.compile(r"(the new yorker|the atlantic|harper'?s magazine).*,\s+\w+\s+\d{1,2},\s+\d{4}", re.I)
DATE_RE   = re.compile(r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b\.?,?\s+\d{1,2},\s+\d{4}", re.I)

# ---------- cleanup ----------
def dehyphenate(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"(?<![.:;])\n(?=[a-z])", " ", text)
    return text

def normalize(text: str) -> str:
    return (text
            .replace("—","-").replace("\u2014","-")
            .replace("’","'").replace("“",'"').replace("”",'"')
            .replace("\u00A0"," "))  # nbsp -> space

# ---------- brand & region ----------
_HARPERS_END_RE = re.compile(
    r"(HARPER[’']?S\s+INDEX|FINDINGS|H\s*A\s*R\s*P\s*E\s*R\s*[’']\s*S\s*I\s*N\s*D\s*E\s*X|F\s*I\s*N\s*D\s*I\s*N\s*G\s*S)",
    re.I
)

def detect_brand_from_text(text: str, pdf_name: str) -> str:
    n = pdf_name.lower(); t = text.lower()
    if "new yorker" in n or "the_new_yorker" in n: return "newyorker"
    if "atlantic" in n: return "atlantic"
    if "harper" in n: return "harpers"
    if "harper's magazine" in t or "harpers magazine" in t or "harper’s magazine" in t: return "harpers"
    if "the new yorker" in t: return "newyorker"
    if "the atlantic" in t: return "atlantic"
    return "auto"

def find_harpers_toc_page(pdf: Path, quiet: bool) -> int:
    for p in range(1, 8):
        try:
            t = pdftotext_extract_page(pdf, p, quiet, mode="layout")
        except Exception:
            continue
        low = t.lower()
        if ("contents" in low or "table of contents" in low) and not _HARPERS_END_RE.search(t):
            if len(re.findall(r"\b\d{1,3}\b", t)) >= 6:
                eprint(f"[harpers] TOC candidate: {p}", quiet)
                return p
    eprint("[harpers] TOC fallback: page 3", quiet)
    return 3

# ---------- patterns ----------
def is_known_section_name(name: str, brand: str) -> bool:
    U = name.strip().upper()
    if brand == "newyorker":
        keys = NY_SECTIONS
    elif brand == "atlantic":
        keys = ATL_SECTIONS
    elif brand == "harpers":
        if "HARPER" in U and "INDEX" in U: return False
        if U.replace(" ","") == "FINDINGS": return False
        keys = HARPERS_SECTIONS
    else:
        keys = NY_SECTIONS + ATL_SECTIONS + HARPERS_SECTIONS
    return any(U.startswith(k) for k in keys)

def valid_page(n: int) -> bool:
    return 1 <= n <= 999

AUTHOR_PAGE_TITLE = re.compile(r"""
    ^
    (?P<author>(?:[A-Z][\w.'’\-]+(?:\s+[A-Z][\w.'’\-]+)*))
    \s{2,}
    (?P<page>\d{1,3})
    \s{2,}
    (?P<title>.+?)
    \s*$
""", re.VERBOSE)

PAGE_TITLE      = re.compile(r"^\s*(?P<page>\d{1,3})\s+(?P<title>.+?)\s*$")
TRAILING_DOTS   = re.compile(r"^(.+?)\s\.{2,}\s(\d{1,3})\s*$")
TRAILING_NUM    = re.compile(r"^(.+?)\s(\d{1,3})\s*$")
SECTION_THEN_PAGE = re.compile(r"^\s*(?P<section>[A-Z][A-Z '&/.\-]+?)\s{2,}(?P<page>\d{1,3})\s*$")

# NEW: permissive leaders: dot, ellipsis, middot, bullet, em/en dashes, thin spaces
LEADERS = r"[.\u2026\u00B7\u2022\u2013\u2014\u2007\u2009\-–—·•]+"
# 1) Title …… Page — Author
TITLE_DOTS_PAGE_AUTHOR = re.compile(rf"^\s*(?P<title>.+?)\s{LEADERS}\s(?P<page>\d{{1,3}})\s*(?:-\s*|—\s*)(?P<author>.+?)\s*$")
# 2) Title — Author …… Page
TITLE_AUTHOR_DOTS_PAGE = re.compile(rf"^\s*(?P<title>.+?)\s*(?:-\s*|—\s*)(?P<author>.+?)\s{LEADERS}\s(?P<page>\d{{1,3}})\s*$")
# 3) Author  Title  Page
AUTHOR_TITLE_PAGE = re.compile(r"^\s*(?P<author>(?:[A-Z][\w.'’\-]+(?:\s+[A-Z][\w.'’\-]+)*))\s{2,}(?P<title>.+?)\s{2,}(?P<page>\d{1,3})\s*$")
# 4) Title …… Page   (no author)
TITLE_DOTS_PAGE = re.compile(rf"^\s*(?P<title>.+?)\s{LEADERS}\s(?P<page>\d{{1,3}})\s*$")
# 5) Title    Page   (spaces only, no leaders)
TITLE_SPACES_PAGE = re.compile(r"^\s*(?P<title>.+?)\s{2,}(?P<page>\d{1,3})\s*$")

# ---------- parsing ----------
def parse(text: str, brand: str, quiet: bool) -> Tuple[Optional[str], Dict[str, Optional[int]], List[TocItem]]:
    items: List[TocItem] = []
    section: Optional[str] = None
    section_pages: Dict[str, Optional[int]] = {}
    issue_title = None

    for L in text.splitlines()[:120]:
        if re.search(r"(The New Yorker|The Atlantic|Harper'?s Magazine).+\d{4}", L, re.I):
            issue_title = L.strip()
            break

    # For Harper's we do NOT slice region — we already restricted to the TOC pages.
    lines = [ln for ln in text.splitlines() if ln.strip()] if brand == "harpers" else [
        ln for ln in slice_region(text, brand).splitlines() if ln.strip()
    ]

    def try_section(line: str) -> Optional[Tuple[str, Optional[int]]]:
        U = line.strip().upper()
        m = re.match(r"^\s*(\d{1,3})\s+(.+?)\s*$", U)  # 15 THE TALK OF THE TOWN
        if m and is_known_section_name(m.group(2), brand):
            pg = int(m.group(1))
            if valid_page(pg): return (m.group(2), pg)
        m2 = SECTION_THEN_PAGE.match(U)  # LETTERS    2
        if m2 and is_known_section_name(m2.group("section"), brand):
            pg = int(m2.group("page"))
            if valid_page(pg): return (m2.group("section"), pg)
        if is_known_section_name(U, brand):
            return (U, None)
        return None

    i = 0
    while i < len(lines):
        raw = lines[i]; line = raw.strip(); U = line.upper()

        if DATE_RE.search(line): i += 1; continue
        if any(noise in U for noise in NOISE_UPPER): i += 1; continue

        sec = try_section(line)
        if sec:
            section, pg = sec
            if section not in section_pages or section_pages[section] is None:
                section_pages[section] = pg
            eprint(f"[parse] Section: {section}" + (f" (p. {pg})" if pg else ""), quiet)
            i += 1; continue

        if section in {"CONTRIBUTORS", "THE MAIL"}:
            i += 1; continue

        # Item patterns (Harper's first)
        m = TITLE_DOTS_PAGE_AUTHOR.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip(); author = m.group("author").strip()
            if valid_page(page): items.append(TocItem(page=page, title=title, section=section, author=author))
            i += 1; continue

        m = TITLE_AUTHOR_DOTS_PAGE.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip(); author = m.group("author").strip()
            if valid_page(page): items.append(TocItem(page=page, title=title, section=section, author=author))
            i += 1; continue

        m = AUTHOR_TITLE_PAGE.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip(); author = m.group("author").strip()
            if valid_page(page) and re.search(r"[a-zA-Z]", title):
                items.append(TocItem(page=page, title=title, section=section, author=author))
            i += 1; continue

        m = TITLE_DOTS_PAGE.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip()
            # Avoid misclassifying section headers as items:
            if not is_known_section_name(title.upper(), brand) and valid_page(page):
                items.append(TocItem(page=page, title=title, section=section))
            i += 1; continue

        m = TITLE_SPACES_PAGE.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip()
            if not is_known_section_name(title.upper(), brand) and valid_page(page):
                items.append(TocItem(page=page, title=title, section=section))
            i += 1; continue

        # Existing generic patterns
        m = AUTHOR_PAGE_TITLE.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip(); author = m.group("author").strip()
            if valid_page(page) and re.search(r"[a-zA-Z]", title):
                if section != "POEMS" and i + 1 < len(lines):
                    nxt = lines[i+1].strip()
                    if (not re.search(r"\d{1,3}\s*$", nxt) and not try_section(nxt) and 10 <= len(nxt) <= 200):
                        title = f"{title} — {nxt}"; i += 1
                items.append(TocItem(page=page, title=title, section=section, author=author))
            i += 1; continue

        m = PAGE_TITLE.match(line)
        if m and section:
            page = int(m.group("page")); title = m.group("title").strip()
            if valid_page(page) and re.search(r"[a-zA-Z]", title):
                items.append(TocItem(page=page, title=title, section=section))
            i += 1; continue

        m = TRAILING_DOTS.match(line) or TRAILING_NUM.match(line)
        if m and section:
            title = m.group(1).strip(); page  = int(m.group(2))
            if not is_known_section_name(title.upper(), brand) and valid_page(page) and re.search(r"[a-zA-Z]", title):
                items.append(TocItem(page=page, title=title, section=section))
            i += 1; continue

        if section == "POEMS" and '"' in line and re.search(r"\d{1,3}", line):
            m2 = re.findall(r"(\"[^\"]+\")\s*(?:-\s*|—\s*)?([^0-9\"“”]+)?\s*(?:\(p\.\s*)?(\d{1,3})\)?", line)
            if m2:
                for t, a, p in m2:
                    page = int(p)
                    if valid_page(page):
                        items.append(TocItem(page=page, title=t.strip(), section=section, author=(a or "").strip() or None))
                i += 1; continue

        i += 1

    # de-dupe + sort
    seen = set(); out: List[TocItem] = []
    for it in items:
        key = (it.page, it.title.lower(), (it.section or ""))
        if key in seen: continue
        seen.add(key); out.append(it)
    out.sort(key=lambda x: (x.page if x.page is not None else 999, (x.section or ""), x.title.lower()))
    return issue_title, section_pages, out

# slice for non-Harper's
def slice_region(text: str, brand: str) -> str:
    low = text.lower()
    start = min([p for p in (low.find("table of contents"), low.find("contents")) if p != -1], default=0)
    text = text[start:]
    out = []
    for ln in text.splitlines():
        if FOOTER_RE.search(ln): break
        out.append(ln.rstrip())
    region = "\n".join(out)
    if brand == "harpers":
        m = _HARPERS_END_RE.search(region)
        if m: region = region[:m.start()]
    return region

# ---------- formatters ----------
def format_plain(issue_title: Optional[str], section_pages: Dict[str, Optional[int]], items: List[TocItem], *,
                 suppress_empty: bool, include_mail: bool, include_contributors: bool) -> str:
    fitems = []
    for it in items:
        if it.section == "THE MAIL" and not include_mail: continue
        if it.section == "CONTRIBUTORS" and not include_contributors: continue
        fitems.append(it)
    items = fitems

    order: List[str] = []
    by_sec: Dict[Optional[str], List[TocItem]] = {}
    for it in items:
        by_sec.setdefault(it.section, []).append(it)
        if it.section and it.section not in order:
            order.append(it.section)

    lines: List[str] = []
    if issue_title: lines += [issue_title, ""]

    for sec, pg in section_pages.items():
        if sec in {"THE MAIL","CONTRIBUTORS"} and not (include_mail if sec=="THE MAIL" else include_contributors): continue
        if suppress_empty and by_sec.get(sec): continue
        lines.append(f"{sec} (p. {pg})" if pg is not None else sec)
    if section_pages: lines.append("")

    for sec in order:
        if sec in {"THE MAIL","CONTRIBUTORS"} and not (include_mail if sec=="THE MAIL" else include_contributors): continue
        pg = section_pages.get(sec)
        lines.append(f"{sec} (p. {pg})" if pg is not None else sec)
        for it in sorted(by_sec.get(sec, []), key=lambda x: (x.page if x.page is not None else 999, x.title.lower())):
            p = f"(p. {it.page})" if it.page is not None else ""
            tail = f" — {it.author}" if it.author else ""
            lines.append(f"• {it.title} {p}{tail}".rstrip())
        lines.append("")
    while lines and not lines[-1].strip(): lines.pop()
    return "\n".join(lines) + "\n"

def format_json(issue_title: Optional[str], section_pages: Dict[str, Optional[int]], items: List[TocItem]) -> str:
    return json.dumps({"issue": issue_title, "sections": section_pages, "items": [asdict(i) for i in items]},
                      ensure_ascii=False, indent=2)

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Extract a plain-text TOC from a magazine PDF")
    ap.add_argument("pdf", type=Path, help="Input PDF")
    ap.add_argument("--pages", type=int, default=16)
    ap.add_argument("--ocr-first", type=int, default=3)
    ap.add_argument("--brand", choices=["auto","newyorker","atlantic","harpers"], default="auto")
    ap.add_argument("--verbose", action="store_true", default=False, help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-suppress-empty", action="store_true")
    ap.add_argument("--include-mail", action="store_true")
    ap.add_argument("--include-contributors", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    quiet = args.quiet
    if getattr(args, "verbose", False) and not quiet:
        eprint(f"[info] PDF: {args.pdf}", quiet)
        eprint(f"[info] Scan pages: {args.pages}", quiet)

    if not args.pdf.exists():
        eprint(f"[err] PDF not found: {args.pdf}", quiet); sys.exit(2)

    # Initial text for brand detection
    text = ""
    try:
        text = pdftotext_extract(args.pdf, args.pages, quiet, mode="layout")
    except Exception as e:
        eprint(f"[warn] layout failed: {e}", quiet)

    if looks_sparse(text):
        eprint(f"[info] Sparse text; OCR first {args.ocr_first} pages...", quiet)
        o = ocr_first_pages(args.pdf, args.ocr_first, quiet)
        if o: text = o

    text = normalize(dehyphenate(text))
    brand = args.brand if args.brand != "auto" else detect_brand_from_text(text, args.pdf.name)
    if getattr(args, "verbose", False) and not quiet:
        eprint(f"[info] Brand: {brand}", quiet)

    # Harper's: TOC page(s) in both modes, merged; do NOT slice
    if brand == "harpers":
        tp = find_harpers_toc_page(args.pdf, quiet)
        t = []
        for mode in ("layout","raw"):
            try:  t.append(normalize(dehyphenate(pdftotext_extract_page(args.pdf, tp, quiet, mode))))
            except Exception: pass
            try:  t.append(normalize(dehyphenate(pdftotext_extract_page(args.pdf, tp+1, quiet, mode))))
            except Exception: pass
        text = "\n".join(filter(None, t))
        eprint(f"[harpers] Using TOC pages {tp}, {tp+1} (layout+raw)", quiet)

    issue, section_pages, items = parse(text, brand, quiet)

    if brand != "harpers" and len(items) < 4:
        try:
            t2 = normalize(dehyphenate(pdftotext_extract(args.pdf, args.pages, quiet, mode="raw")))
            issue2, sec2, it2 = parse(t2, brand, quiet)
            if len(it2) > len(items): issue, section_pages, items = issue2, sec2, it2
        except Exception as e:
            eprint(f"[warn] raw failed: {e}", quiet)

    out = format_json(issue, section_pages, items) if args.json else format_plain(
        issue, section_pages, items,
        suppress_empty=(not args.no_suppress_empty),
        include_mail=args.include_mail,
        include_contributors=args.include_contributors,
    )

    if args.out:
        args.out.write_text(out, encoding="utf-8")
        if getattr(args, "verbose", False) and not quiet: eprint(f"[ok] Wrote: {args.out}", quiet)
    else:
        print(out)

if __name__ == "__main__":
    main()
