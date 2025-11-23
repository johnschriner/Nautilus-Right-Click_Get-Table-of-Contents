#!/usr/bin/env bash
# GetMagazineTOC — Nautilus wrapper calling get_mag_toc.py with robust logging and Zenity output.

set -Eeuo pipefail

: "${PYBIN:=$HOME/.venvs/nautilus-pdf/bin/python}"
PY_SCRIPT="$HOME/.local/share/nautilus/scripts-support/get_mag_toc.py"

PAGES="${PAGES:-16}"
OCR_FIRST="${OCR_FIRST:-3}"
BRAND="${BRAND:-auto}"             # auto-detect brand by default
INCLUDE_MAIL="${INCLUDE_MAIL:-1}"   # 1=include (toggle later if you want)
INCLUDE_CONTRIB="${INCLUDE_CONTRIB:-1}"
SUPPRESS_EMPTY="${SUPPRESS_EMPTY:-0}"
LOGDIR="$HOME/.cache"
LOGFILE="$LOGDIR/get_mag_toc.log"
mkdir -p "$LOGDIR"

# Let zenity work from Nautilus
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" | tee -a "$LOGFILE" >&2; }
die() {
  local msg="${1:-Unknown error}"
  log "ERROR: $msg"
  tail -n 120 "$LOGFILE" >&2 || true
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title="Magazine TOC (failed)" \
           --text="$(printf '%s\n\n(See %s for details.)' "$msg" "$LOGFILE")" || true
  fi
  exit 1
}

{
  echo
  echo "==================== $(ts) ===================="
  echo "Launching GetMagazineTOC"
  echo "PYBIN=$PYBIN"
  echo "PY_SCRIPT=$PY_SCRIPT"
  echo "PAGES=$PAGES OCR_FIRST=$OCR_FIRST BRAND=$BRAND"
} >> "$LOGFILE"

# Gather selection (Nautilus env or CLI args)
collect_selection() {
  if [[ $# -gt 0 ]]; then printf '%s\n' "$@"; return; fi
  if [[ -n "${NAUTILUS_SCRIPT_SELECTED_FILE_PATHS-}" ]]; then printf '%s\n' "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS"; return; fi
  die "No files selected. Invoke from Nautilus or pass file paths as arguments."
}
mapfile -t FILES < <(collect_selection "$@")
(( ${#FILES[@]} >= 1 )) || die "No input files."

# Quick tool checks
command -v "$PYBIN" >/dev/null 2>&1 || die "Python not found at $PYBIN"
command -v pdftotext >/dev/null 2>&1 || die "pdftotext (poppler-utils) not found."
command -v pdftoppm >/dev/null 2>&1 || log "pdftoppm not found (OCR fallback may be skipped)."
command -v tesseract >/dev/null 2>&1 || log "tesseract not found (OCR fallback may be skipped)."
[[ -f "$PY_SCRIPT" ]] || die "get_mag_toc.py not found at $PY_SCRIPT"

{
  "$PYBIN" --version 2>&1 | sed 's/^/[ver] /'
  pdftotext -v 2>&1 | head -1 | sed 's/^/[ver] /'
  pdftoppm -v 2>&1 | head -1 | sed 's/^/[ver] /' || true
  tesseract --version 2>&1 | head -1 | sed 's/^/[ver] /' || true
} >> "$LOGFILE"

for PDF in "${FILES[@]}"; do
  [[ -f "$PDF" ]] || { log "Skipping non-file: $PDF"; continue; }
  log "Processing: $PDF"

  TOC_OUT="$("$PYBIN" "$PY_SCRIPT" \
      "$PDF" \
      --brand "$BRAND" \
      --pages "$PAGES" \
      --ocr-first "$OCR_FIRST" \
      --verbose \
      $( [[ "$INCLUDE_MAIL" == "1" ]] && printf -- '--include-mail ' ) \
      $( [[ "$INCLUDE_CONTRIB" == "1" ]] && printf -- '--include-contributors ' ) \
      2>>"$LOGFILE")" || die "TOC extraction failed for: $PDF"

  outlen=${#TOC_OUT}
  if (( outlen < 60 )); then
    log "WARN: Very short output (${outlen} chars). Check $LOGFILE if this seems wrong."
  fi

  if command -v zenity >/dev/null 2>&1; then
    printf '%s\n' "$TOC_OUT" | \
      zenity --text-info --width=820 --height=920 \
             --title="Table of Contents — $(basename "$PDF")" \
             --ok-label="Copy & Close"
  else
    log "zenity not available; printing TOC to stdout:"
    printf '%s\n' "$TOC_OUT"
  fi

  log "Done: $PDF"
done

log "All done."
exit 0
