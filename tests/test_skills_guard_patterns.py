"""Hermes skills-guard blocks a skill outright (critical → dangerous, --force cannot override) when any
file contains these literals. Docs mentioning them were enough to block youtube-summary (2026-09-26)."""
import re
import unittest
from pathlib import Path

CRITICAL = [r"\$HOME/\.hermes/\.env", r"~/\.hermes/\.env"]   # tools/skills_guard.py: hermes_env_access


class NoCriticalPatterns(unittest.TestCase):
    def test_skills_have_no_critical_guard_patterns(self):
        hits = []
        for f in (Path(__file__).parent.parent / "skills").rglob("*"):
            if f.is_file():
                text = f.read_text(errors="ignore")
                hits += [f"{f}: {p}" for p in CRITICAL if re.search(p, text)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
