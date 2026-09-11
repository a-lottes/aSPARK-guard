#!/usr/bin/env python3
"""Entry point for every aspark-guard hook.

Usage (from `hooks/hooks.json`, with the payload on stdin):

    guard.py pre-tool-use | post-tool-use | subagent-stop | session-start

And, for checking an install by hand:

    guard.py scan [path]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aspark_guard.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
