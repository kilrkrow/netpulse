"""No UTF-8 ellipsis or smart punctuation anywhere visible: every source string stays ASCII."""

import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_python_sources_are_ascii_only():
    bad = []
    for pat in ("core/**/*.py", "ui/**/*.py", "main.py", "main_classic.py"):
        for path in glob.glob(os.path.join(ROOT, pat), recursive=True):
            text = open(path, encoding="utf-8").read()
            for n, line in enumerate(text.splitlines(), 1):
                if any(ord(c) > 127 for c in line):
                    bad.append(f"{os.path.relpath(path, ROOT)}:{n}")
    assert not bad, "non-ASCII characters in: " + ", ".join(bad[:20])
