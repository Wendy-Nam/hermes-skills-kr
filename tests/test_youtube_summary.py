"""Offline checks for skills/youtube-summary (no network: every path here fails before any HTTP call)."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "skills" / "youtube-summary" / "scripts"
URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def run(script, *args, env_extra=None):
    home = tempfile.mkdtemp()
    env = {k: v for k, v in os.environ.items()
           if k not in ("GEMINI_API_KEY", "APIFY_TOKEN", "WEBSHARE_PROXY_USERNAME", "HERMES_SCRAPER_PROXY",
                        "HERMES_DATA")}
    env.update(HERMES_HOME=home, **(env_extra or {}))
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True,
                          env=env, timeout=60)


class GeminiVideo(unittest.TestCase):
    def test_rejects_non_youtube_url(self):
        r = run("gemini_video.py", "https://example.com/video")
        self.assertEqual(r.returncode, 2)
        self.assertIn("YouTube URL", r.stderr)

    def test_missing_key_exits_3_with_setup_hint(self):
        r = run("gemini_video.py", URL)
        self.assertEqual(r.returncode, 3)
        self.assertIn("GEMINI_API_KEY", r.stderr)

    def test_key_read_from_hermes_home_env_file(self):
        home = Path(tempfile.mkdtemp())
        (home / ".env").write_text("OTHER=1\nGEMINI_API_KEY='k-from-file'\n")
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["HERMES_HOME"] = str(home)
        spec = importlib.util.spec_from_file_location("gv", SCRIPTS / "gemini_video.py")
        gv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gv)
        self.assertEqual(gv._key(), "k-from-file")


class Yt(unittest.TestCase):
    def test_without_any_key_fails_honestly_and_skips_apify(self):
        r = run("yt.py", URL, "--apify-first")
        self.assertEqual(r.returncode, 1)
        self.assertIn("APIFY_TOKEN 없음", r.stderr)      # no ledger module needed anymore
        self.assertIn("GEMINI_API_KEY", r.stderr)          # then Gemini fallback reports the missing key
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
