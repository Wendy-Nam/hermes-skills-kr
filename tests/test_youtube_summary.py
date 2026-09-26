"""Offline checks for skills/youtube-summary (no network: every path here fails before any HTTP call)."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).parent.parent / "skills" / "youtube-summary" / "scripts"
URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_CRED_ENV_KEYS = ("GEMINI_API_KEY", "APIFY_TOKEN", "HERMES_DATA")


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
        with patch.dict(os.environ, {"HERMES_HOME": str(home)}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)      # 파일 값만 쓰게 한다
            spec = importlib.util.spec_from_file_location("gv", SCRIPTS / "gemini_video.py")
            gv = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gv)
            self.assertEqual(gv._key(), "k-from-file")


def load_yt():
    """yt.py를 모듈로 읽는다(import 시점에는 아무 것도 실행되지 않는다)."""
    spec = importlib.util.spec_from_file_location("yt", SCRIPTS / "yt.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Yt(unittest.TestCase):
    def _env(self, home, **extra):
        """os.environ을 오염시키지 않고 HERMES_HOME(및 키 값)을 지정한다 — 테스트 간 상태 누수 방지."""
        clean = {k: v for k, v in os.environ.items()
                 if k not in _CRED_ENV_KEYS and not k.startswith(("WEBSHARE_", "HERMES_SCRAPER_"))}
        clean["HERMES_HOME"] = str(home)
        clean.update(extra)
        return patch.dict(os.environ, clean, clear=True)

    def test_without_any_key_fails_honestly_and_skips_apify(self):
        r = run("yt.py", URL, "--apify-first")
        self.assertEqual(r.returncode, 1)
        self.assertIn("APIFY_TOKEN 없음", r.stderr)      # no ledger module needed anymore
        self.assertIn("GEMINI_API_KEY", r.stderr)          # then Gemini fallback reports the missing key
        self.assertNotIn("Traceback", r.stderr)

    def test_no_url_is_a_usage_error_not_a_traceback(self):   # was: IndexError on sys.argv[1]
        for args in ([], ["--raw"], ["--prompt", "요약해줘"]):
            r = run("yt.py", *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("사용법", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_flags_before_url_still_parse(self):             # was: "--raw" taken as the URL
        self.assertEqual(load_yt()._parse(["--raw", URL]), (URL, [], {"--raw"}))
        self.assertEqual(load_yt()._parse([URL, "--apify-first", "--no-apify"]), (URL, [], {"--apify-first", "--no-apify"}))
        self.assertEqual(load_yt()._parse([URL, "--prompt", "요약", "--fast"]),
                         (URL, ["--prompt", "요약", "--fast"], set()))

    def test_prompt_value_is_never_mistaken_for_the_url(self):   # --prompt 뒤 값은 값이다
        self.assertEqual(load_yt()._parse(["--prompt", "https://youtu.be/dQw4w9WgXcQ", URL]),
                         (URL, ["--prompt", "https://youtu.be/dQw4w9WgXcQ"], set()))

    def test_raw_never_falls_back_to_a_gemini_summary(self):  # contract: --raw means transcript or nothing
        r = run("yt.py", URL, "--raw", env_extra={"GEMINI_API_KEY": "k"})   # 키가 있어도 요약으로 바꾸지 않는다
        self.assertEqual(r.returncode, 1)
        self.assertIn("--raw: 자막을 못 얻었습니다", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.stdout.strip(), "")   # 요약 본문이 출력되지 않았어야 한다

    def test_child_env_merges_env_file_values(self):   # was: .env read here, os.environ-only in the child → 프록시 없이 요청됨
        home = Path(tempfile.mkdtemp())
        (home / ".env").write_text("WEBSHARE_PROXY_USERNAME=u\nHERMES_SCRAPER_PROXY=http://h:1\n")
        with self._env(home):
            env = load_yt()._child_env()
        self.assertEqual(env.get("WEBSHARE_PROXY_USERNAME"), "u")
        self.assertEqual(env.get("HERMES_SCRAPER_PROXY"), "http://h:1")

    def test_child_env_does_not_override_real_environment(self):
        home = Path(tempfile.mkdtemp())
        (home / ".env").write_text("GEMINI_API_KEY=from-file\n")
        with self._env(home, GEMINI_API_KEY="from-env"):
            self.assertEqual(load_yt()._child_env()["GEMINI_API_KEY"], "from-env")

    def test_https_proxy_alone_counts_as_residential(self):   # fetch_transcript.py는 HTTPS_PROXY를 프록시로 본다
        home = Path(tempfile.mkdtemp())
        (home / ".env").write_text("HTTPS_PROXY=http://h:1\n")
        with self._env(home):
            yt = load_yt()
            self.assertTrue(yt._residential())
            self.assertEqual(yt._child_env()["HTTPS_PROXY"], "http://h:1")

    def test_no_proxy_means_no_residential_attempt(self):
        with self._env(Path(tempfile.mkdtemp())):
            self.assertFalse(load_yt()._residential())

    def test_raw_with_no_apify_says_why_instead_of_failing_silently(self):   # was: 0 bytes out, 0 bytes err
        r = run("yt.py", URL, "--raw", "--no-apify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--no-apify", r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_transcript_files_of_different_urls_do_not_collide(self):   # was: every unparsable URL → yt-video.txt
        v = load_yt()._vid
        self.assertEqual(v(URL), "dQw4w9WgXcQ")
        self.assertNotEqual(v("https://vimeo.com/12345"), "video")
        self.assertNotEqual(v("https://vimeo.com/12345"), v("https://vimeo.com/67890"))


class Timestamps(unittest.TestCase):
    """자막 3경로(자막 API·Apify·프롬프트)가 같은 표기를 쓰는지."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("ft", SCRIPTS / "fetch_transcript.py")
        self.ft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ft)
        self.yt = load_yt()

    def test_all_three_sources_agree_on_format(self):
        self.assertEqual(self.ft.format_tag(0), "[00:00]")
        self.assertEqual(self.ft.format_tag(6005), "[1:40:05]")     # 100분 → 시 단위로, [100:05]가 되지 않는다
        self.assertEqual([self.yt._stamp(s) for s in (0, 65, 6005, 3723)],
                         ["[00:00]", "[01:05]", "[1:40:05]", "[1:02:03]"])
        self.assertEqual(self.ft.format_tag(6005), self.yt._stamp(6005))

    def test_long_video_stamp_is_still_linkified(self):
        spec = importlib.util.spec_from_file_location("gv3", SCRIPTS / "gemini_video.py")
        gv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gv)
        self.assertIn("t=6005", gv._linkify("결론 [100:05]", "dQw4w9WgXcQ"))
        self.assertIn("t=5", gv._linkify("설명 [00:05 - 100:14]", "dQw4w9WgXcQ"))   # 구간도 3자리 분 허용



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
