"""Portable PRD Flow launcher.

Run this file directly from an extracted skill package; it places the bundled
``prd_flow`` package on Python's normal script path without asking callers to
set ``PYTHONPATH``.
"""
import sys

# The workflow accepts and emits UTF-8 irrespective of the active Windows
# console code page.  This also makes redirected logs machine-readable.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from prd_flow.main import main


if __name__ == "__main__":
    raise SystemExit(main())
