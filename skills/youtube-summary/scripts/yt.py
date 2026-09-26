#!/usr/bin/env python3
"""유튜브 진입점. 기본 순서 = 가장 빠른 것부터:
  ① Gemini가 영상을 직접 봄(요약·질문답, 3분 영상 ~20초·24분 ~30초)
  ② 실패(503 체인 소진·비공개/연령제한·키 없음)면 APIFY_TOKEN이 있을 때만 Apify 자막 액터(영상당 약 $0.005, 무료 월 $5 크레딧) → 자막을 Gemini 텍스트 모드로 정리, 그것도 안 되면 자막 원문 출력
  ⓪ residential 프록시(WEBSHARE_PROXY_USERNAME / HERMES_SCRAPER_PROXY)가 있을 때만 맨 앞에 자막 API 1회(3초, 정확 인용)
  yt.py <url> [--prompt "..."] [--raw] [--apify-first] [--no-apify] [--try-direct] [--fast|--hq|--model ...]
--raw: 정리 없이 자막 원문만(Apify/자막API) — 정확한 인용용. 자막을 못 얻으면 요약으로 대체하지 않고 실패(exit 1).
     자막은 확보되면 항상 $HERMES_HOME/tmp/yt-<id>.txt에도 저장."""
import hashlib
import json, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("HERMES_HOME") or os.environ.get("HERMES_DATA") or os.path.expanduser("~/.hermes")
ACTOR = "starvibe~youtube-video-transcript"     # 원어 자막 + 메타데이터, $0.005/영상 (2026-09-12 실측 19s)

# yt.py만 아는 플래그(gemini_video.py로 넘기지 않는다) / 값을 요구하는 플래그 / 값 없는 플래그
_KIT_FLAGS = {"--raw", "--apify-first", "--no-apify", "--try-direct"}
_VALUE_FLAGS = {"--prompt", "--model", "--fps", "--text-file"}
_PASS_FLAGS = _KIT_FLAGS | {"--lowres", "--hq", "--fast", "--json"}
# fetch_transcript.py가 프록시로 인정하는 변수 — 그 정의와 같은 목록이어야 한다(M4)
_PROXY_VARS = ("WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD",
               "HERMES_SCRAPER_PROXY", "HTTPS_PROXY", "https_proxy")
_CREDENTIALS = ("GEMINI_API_KEY", "APIFY_TOKEN") + _PROXY_VARS


def _parse(argv):
    """(url, gemini로 넘길 인자, yt 플래그). URL이 플래그보다 앞에 와야 하지만, 앞에 와도 되게 파싱한다."""
    url, rest, flags, i = None, [], set(), 0
    while i < len(argv):
        a = argv[i]
        if a in _PASS_FLAGS:
            flags.update([a] if a in _KIT_FLAGS else [])
            if a not in _KIT_FLAGS:
                rest.append(a)
            i += 1
        elif a in _VALUE_FLAGS:
            rest.append(a)
            if i + 1 < len(argv):
                rest.append(argv[i + 1])
            i += 2
        elif a.startswith("-"):
            rest.append(a); i += 1
        elif url is None:
            url = a; i += 1
        else:
            rest.append(a); i += 1
    return url, rest, flags


def _die(msg, code=2):
    print(f"[yt] {msg}", file=sys.stderr)
    sys.exit(code)


url, rest, flags, GEM = "", [], set(), []


def _vid(u):
    """11자 영상 ID. URL에서 못 뽑으면 URL 해시를 써서 서로 다른 URL이 같은 파일명을 갖지 않게 한다."""
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})", u)
    return m.group(1) if m else "url-" + hashlib.sha1(u.encode("utf-8")).hexdigest()[:8]


def _stamp(sec):
    """[mm:ss] 또는 1시간 넘으면 [h:mm:ss] — 자막·링크 변환·출력 형식 문서가 공유하는 유일한 표기."""
    t = int(sec)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"


def _env(key):
    v = os.environ.get(key, "").strip()
    if v:
        return v
    try:
        with open(os.path.join(DATA, ".env"), encoding="utf-8") as f:
            for ln in f:
                if ln.startswith(key + "="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _child_env():
    """하위 프로세스(자막 API·Gemini)에 넘길 환경. 이 스크립트는 .env 파일을 직접 읽는데
    fetch_transcript.py·gemini_video.py는 os.environ만 본다 — 값이 .env에만 있으면 프록시 없이
    요청해 VPS IP로 차단당한다. 읽어 둔 값을 그대로 넘겨 두 경로의 기준을 맞춘다."""
    env = dict(os.environ)
    for k in _CREDENTIALS:
        if not os.environ.get(k) and _env(k):
            env[k] = _env(k)
    return env


def _residential():
    """자막 API를 맨 앞에서 시도할 만큼 프록시가 있는가. fetch_transcript.py의 프록시 슬롯 정의와
    반드시 같은 목록을 쓴다 — 여기만 좁으면 "프록시 설정했는데 안 되는" 상태가 된다."""
    return any(_env(k) for k in _PROXY_VARS)


def gemini_video():
    """① 영상 직접 시청. 성공하면 종료(출력은 gemini_video.py가 직접 찍음)."""
    return subprocess.call(GEM + rest, env=_child_env()) == 0


def transcript_api():
    """⓪ youtube-transcript-api (residential 프록시 경유). 성공 시 텍스트, 아니면 None."""
    try:
        import youtube_transcript_api          # noqa: F401  — 설치돼 있는지 먼저 확인(없으면 조용히 실패하지 않게)
    except ImportError:
        print("[자막 API 건너뜀: youtube-transcript-api 미설치 — pip install youtube-transcript-api]", file=sys.stderr)
        return None
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "fetch_transcript.py"), url, "--text-only", "--timestamps"],
                           capture_output=True, text=True, timeout=60, env=_child_env())
        if r.returncode == 0 and len(r.stdout.strip()) > 200 and '"error"' not in r.stdout[:200]:
            return "[transcript]\n" + r.stdout.strip()
    except Exception:
        pass
    return None


def apify_transcript():
    """② Apify 액터 (APIFY_TOKEN 있을 때만). 무료 플랜은 월 크레딧이 바닥나면 402로 멈추므로 과금 폭주는 없다. (텍스트, 실패사유)"""
    tok = _env("APIFY_TOKEN")
    if not tok:
        return None, "APIFY_TOKEN 없음"
    req = urllib.request.Request(   # 토큰은 URL이 아니라 헤더로 — 프록시·로그에 남지 않게
        f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?timeout=120&format=json",
        data=json.dumps({"youtube_url": url, "include_transcript_text": True}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"}, method="POST")
    try:
        items = json.load(urllib.request.urlopen(req, timeout=150))
    except Exception as e:
        return None, f"apify {type(e).__name__}: {str(e)[:80]}"
    if not items or not items[0].get("transcript"):
        return None, "apify: 자막 없음(자막 꺼진 영상)"
    it = items[0]
    head = (f"[transcript via apify] {it.get('title','')} · {it.get('channel_name','')} · "
            f"{int(it.get('duration_seconds') or 0)//60}분 · lang={it.get('language') or it.get('transcript_language') or '?'}")
    return "\n".join([head] + [f"{_stamp(s['start'])} {s['text']}"
                              for s in it["transcript"] if s.get("text")]), None


def deliver(text, source):
    """자막 확보 후: 파일 저장 → (--raw면 원문) → Gemini 텍스트 정리 → 그것도 실패면 원문."""
    path = os.path.join(DATA, "tmp", f"yt-{_vid(url)}.txt"); os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: f.write(text)
    note = f"[자막 원문({source}, {text.count(chr(10))+1}줄): {path} — 정확한 인용은 grep/read_file]"
    if "--raw" in flags or subprocess.call(GEM + ["--text-file", path] + rest, env=_child_env()) != 0:
        print(text)
    print("\n" + note)
    return 0


def main(argv):
    global url, rest, flags, GEM
    url, rest, flags = _parse(argv)
    if not url:
        _die('사용법: yt.py "<유튜브 URL>" [--prompt "..."] [--raw] [--apify-first] [--no-apify] [--try-direct]')
    GEM = [sys.executable, os.path.join(HERE, "gemini_video.py"), url]

    # --raw 계약: "원문만". 어떤 경로에서도 요약으로 대체하지 않는다(요약이 섞이면 정확한 인용이 무효가 된다).
    raw = "--raw" in flags
    if "--try-direct" in flags or _residential():
        t = transcript_api()
        if t:
            return deliver(t, "youtube-transcript-api")
        print("[자막 API 실패]", file=sys.stderr)
    if not raw and "--apify-first" not in flags:
        if gemini_video():
            return 0
        print("[gemini 영상 모드 실패 → apify]", file=sys.stderr)
    if "--no-apify" not in flags:
        t, why = apify_transcript()
        if t:
            return deliver(t, "apify")
        print(f"[apify 불가: {why}]", file=sys.stderr)
    elif raw:
        print("[--raw: --no-apify라 자막을 얻을 경로가 없습니다]", file=sys.stderr)
    if raw:
        print("[--raw: 자막을 못 얻었습니다 — 요약으로 대체하지 않고 실패]", file=sys.stderr)
        return 1
    if "--apify-first" in flags:
        return 0 if gemini_video() else 1
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
