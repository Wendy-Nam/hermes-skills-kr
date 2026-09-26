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



class Linkify(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("gv2", SCRIPTS / "gemini_video.py")
        self.gv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gv)

    def test_mm_ss_and_h_mm_ss_become_links_without_previews(self):
        out = self.gv._linkify("요지 [03:12] 그리고 [1:02:03].", "dQw4w9WgXcQ")
        self.assertEqual(out, "요지 [03:12](<https://youtu.be/dQw4w9WgXcQ?t=192>) "
                              "그리고 [1:02:03](<https://youtu.be/dQw4w9WgXcQ?t=3723>).")

    def test_ranges_link_to_their_start(self):   # real Gemini output, 2026-09-26
        out = self.gv._linkify("설명 [00:05 - 00:14] 끝 [1:00–1:30]", "jNQXAC9IVRw")
        self.assertEqual(out, "설명 [00:05 - 00:14](<https://youtu.be/jNQXAC9IVRw?t=5>) "
                              "끝 [1:00–1:30](<https://youtu.be/jNQXAC9IVRw?t=60>)")

    def test_already_linked_and_non_timestamps_untouched(self):
        s = "[03:12](https://x) [주의] [12:3] [ab:cd]"
        self.assertEqual(self.gv._linkify(s, "dQw4w9WgXcQ"), s)

    def test_video_id_from_url_forms(self):
        for u in ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ",
                  "https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/live/dQw4w9WgXcQ"):
            self.assertEqual(self.gv._vid(u), "dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
