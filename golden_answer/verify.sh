#!/usr/bin/env bash
#
# Golden answer verification.
#
#   1. pick a Python interpreter
#   2. build a clean virtual environment (unless VERIFY_PYTHON is supplied)
#   3. install requirements.txt
#   4. point the app at a throw-away SQLite file
#   5. run the full suite over two real uvicorn workers for the concurrency part
#   6. probe the storage-level invariant guards directly
#   7. probe the golden-test coverage matrix
#   8. write the raw output to verify_doc/test-result.txt and propagate the exit code
#
# Usage:
#   ./verify.sh                       # full clean run
#   VERIFY_PYTHON=/path/to/python ./verify.sh
#   VERIFY_SKIP_VENV=1 ./verify.sh    # reuse the current interpreter
#
# Portability note: after `cd "$HERE"` the script only ever hands *relative*
# paths to native tools. On Windows a Git-Bash absolute path (/c/Users/...)
# reaches python.exe/pip.exe unconverted unless the MSYS argument mangling
# happens to kick in, which it does not when the script is launched from a
# non-MSYS parent process. Relative paths remove the whole class of failure.
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1

LOG_FILE="${VERIFY_LOG:-verify_doc/test-result.txt}"
mkdir -p "$(dirname "$LOG_FILE")"

# ---------------------------------------------------------------- interpreter
if [[ -n "${VERIFY_PYTHON:-}" ]]; then
  PY="$VERIFY_PYTHON"
  SKIP_VENV=1
elif [[ "${VERIFY_SKIP_VENV:-0}" == "1" ]]; then
  SKIP_VENV=1
  PY="$(command -v python3 || command -v python)"
else
  SKIP_VENV=0
  PY="$(command -v python3 || command -v python)"
fi

if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "ERROR: no usable Python interpreter (set VERIFY_PYTHON)" >&2
  exit 127
fi

echo "== workspace: $HERE"
echo "== interpreter: $PY"
"$PY" -c "import sys; print('== version:', sys.version.replace(chr(10), ' '))"

# ------------------------------------------------------------ clean venv
if [[ "$SKIP_VENV" != "1" ]]; then
  VENV=".venv"
  if [[ -f "$VENV/pyvenv.cfg" ]]; then
    echo "== removing existing virtualenv at $VENV"
    rm -rf "$VENV"
  fi
  echo "== creating virtualenv at $VENV"
  "$PY" -m venv "$VENV" || exit 2
  if [[ -x "$VENV/Scripts/python.exe" ]]; then
    PY="$VENV/Scripts/python.exe"
  else
    PY="$VENV/bin/python"
  fi
  echo "== venv python: $PY"
else
  echo "== reusing interpreter (no venv created)"
fi

# ------------------------------------------------------------ dependencies
echo "== installing requirements"
"$PY" -m pip install --quiet --upgrade pip || exit 3
"$PY" -m pip install --quiet -r requirements.txt || exit 3
echo "== installed:"
"$PY" -m pip list 2>/dev/null | grep -Ei 'fastapi|uvicorn|pytest|httpx' || true

# ---------------------------------------------------- isolated runtime state
# mktemp is not reliable everywhere (Git-Bash on Windows rejects `-t <name>`
# templates without X's and may fail outright when TMPDIR is unset), so the
# temp dir is resolved defensively: try mktemp, then fall back to a directory
# next to this script. An empty WORKDIR would silently turn the DB path into a
# drive-root path ("/verify.db" -> "C:\verify.db"), which is exactly the kind of
# environment leak this script is supposed to avoid.
WORKDIR=""
for CANDIDATE in "$(mktemp -d 2>/dev/null || true)" \
                 "$(mktemp -d -t refund_verify_XXXXXX 2>/dev/null || true)" \
                 "${TMPDIR:-}" "${TEMP:-}" "${TMP:-}"; do
  if [[ -n "$CANDIDATE" && -d "$CANDIDATE" && -w "$CANDIDATE" ]]; then
    WORKDIR="$CANDIDATE"
    break
  fi
done
if [[ -z "$WORKDIR" ]]; then
  WORKDIR="$HERE/.verify-work"
  mkdir -p "$WORKDIR" || exit 4
  echo "== mktemp/TMPDIR unavailable; using $WORKDIR"
fi
DB_DIR="$WORKDIR"
if command -v cygpath >/dev/null 2>&1; then
  # a native interpreter must receive a Windows path, not /tmp/...
  DB_DIR_WIN="$(cygpath -w "$WORKDIR" 2>/dev/null || true)"
  [[ -n "$DB_DIR_WIN" ]] && DB_DIR="$DB_DIR_WIN"
fi
export REFUND_DB_PATH="$DB_DIR/verify.db"

# the temp workspace is ours; remove it on the way out in every exit path
cleanup() {
  if [[ -n "${WORKDIR:-}" && "$WORKDIR" != "/" ]]; then
    rm -rf "$WORKDIR" 2>/dev/null || true
  fi
  return 0
}
trap cleanup EXIT
export REFUND_GATEWAY_MODE="${REFUND_GATEWAY_MODE:-ok}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

echo "== database: $REFUND_DB_PATH"
echo "== running golden test suite"
echo

# ---------------------------------------------------------------- test run
"$PY" -m pytest tests -rA 2>&1 | tee "$LOG_FILE"
STATUS="${PIPESTATUS[0]}"

# ------------------------------------------- storage-level invariant probe
# The concurrency tests prove the business outcome under real races. This probe
# removes the timing luck: it checks that the database rejects the illegal write
# itself, whatever the application code does.
{
  echo
  echo "================================================================"
  echo "storage-level invariant probe (verify_doc/check_db_guards.py)"
  echo "================================================================"
} | tee -a "$LOG_FILE"
"$PY" verify_doc/check_db_guards.py 2>&1 | tee -a "$LOG_FILE"
GUARD_STATUS="${PIPESTATUS[0]}"

# ------------------------------------------------- coverage matrix probe
{
  echo
  echo "================================================================"
  echo "golden-test coverage probe (verify_doc/check_coverage_matrix.py)"
  echo "================================================================"
} | tee -a "$LOG_FILE"
"$PY" verify_doc/check_coverage_matrix.py 2>&1 | tee -a "$LOG_FILE"
COVERAGE_STATUS="${PIPESTATUS[0]}"

for EXTRA in "$GUARD_STATUS" "$COVERAGE_STATUS"; do
  if [[ "$STATUS" -eq 0 && "$EXTRA" -ne 0 ]]; then
    STATUS="$EXTRA"
  fi
done

echo
echo "== exit code: $STATUS"
echo "== log written to: $HERE/$LOG_FILE"
exit "$STATUS"
