---
name: youtube-summary
description: "유튜브 링크를 한국어로 요약·질문답·챕터·스레드로 정리 (Gemini가 영상을 직접 봄, VPS IP 차단 무관)."
platforms: [linux, macos, windows]
---

# YouTube 요약

`SKILL_DIR` = 이 SKILL.md가 있는 디렉터리. 스크립트는 파이썬 표준 라이브러리만 쓴다(자막 API 경로만 `youtube-transcript-api` 필요).

## 준비물

- **필수**: `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey) 무료 키. 환경변수 또는 `$HERMES_HOME/.env`(Docker 기본 `/opt/data/.env`, 일반 설치 `~/.hermes/.env`)에 한 줄. 스크립트가 직접 읽으므로 재시작 불필요.
- 선택: `APIFY_TOKEN` — Gemini가 못 보는 영상(비공개 직전·일부 지역 제한 등)의 자막 폴백. 영상당 약 $0.005, 무료 플랜 월 $5 크레딧(소진 시 Apify가 멈춤).
- 선택: `WEBSHARE_PROXY_USERNAME`/`WEBSHARE_PROXY_PASSWORD`(residential) 또는 `HERMES_SCRAPER_PROXY` — 있으면 자막 API를 맨 앞에서 3초 시도(정확한 인용용).

## 사용 — `yt.py` 하나로

```bash
python3 SKILL_DIR/scripts/yt.py "URL"                                   # ① Gemini가 영상을 직접 봄 → 실패 시 ② Apify 자막→Gemini 텍스트 정리 → 그것도 실패면 자막 원문
python3 SKILL_DIR/scripts/yt.py "URL" --prompt "질문 / 챕터 / 스레드 형식"   # 정리 형식·질문 (기본: 논지 중심 정리)
python3 SKILL_DIR/scripts/yt.py "URL" --raw                              # 자막 원문(타임스탬프)만 — 정확한 인용용
python3 SKILL_DIR/scripts/yt.py "URL" --apify-first                      # 자막 기반 정리를 우선(발화 인용 정밀)
python3 SKILL_DIR/scripts/yt.py "URL" --hq                               # 화면·슬라이드가 중요할 때(1fps·풀해상도, 2배 느림)
python3 SKILL_DIR/scripts/yt.py "URL" --fast                             # 속도 우선(lite 모델)
```

- **Gemini 출력은 완성본**: 구조·문장 그대로 전달(긴 건 여러 메시지로 나뉘어도 됨). 압축·전보체 금지. 네 말은 앞뒤 한 줄씩만.
- 자막이 확보되면 `$HERMES_HOME/tmp/yt-<id>.txt`에 저장된다(출력 끝에 경로). 정확한 문장이 필요하면 `grep`/`read_file`로 **부분만** 읽는다.
- 전부 실패해서 자막 파일로 직접 정리하게 되면(드묾): 아래 '설명 방식' + **메신저 가독성**(포인트마다 굵은 제목 한 줄 → 본문 2~3문장 → 빈 줄, 한 덩어리 벽글 금지).
- VPS·데이터센터 IP는 유튜브가 자막 API를 막는다. 반복 재시도, yt-dlp, 쿠키, 브라우저 스크래핑은 하지 않는다. 전부 실패하면 정직하게 보고.

## When to use

유저가 유튜브 URL을 주거나, 영상 요약·자막·챕터·스레드·블로그 변환을 요청할 때.

## Output Formats

- **Summary**(기본): 요지 + 핵심 포인트(타임스탬프) + 한계·반론 + 인용 + 대상
- **Chapters**: 주제 전환 기준 타임스탬프 목록
- **Thread**: X 스레드(각 280자 이하)
- **Blog post**: 제목·섹션·핵심 정리
- **Quotes**: 타임스탬프 달린 인용

원하는 형식은 `--prompt`로 그대로 요청하면 Gemini가 영상을 보고 맞춰 준다. 예시는 `references/output-formats.md`.

## 설명 방식 (자막을 직접 정리할 때)

완결된 문장으로. 단어 나열·전보체·화살표 축약 금지. 각 포인트는 '주장 → 근거(수치·사례·인용) → 함의'가 드러나게, 근거 위치는 [mm:ss]. 처음 나오는 용어·고유명사는 한 번 풀어 쓰기. 영상 안 본 사람이 읽고 대화에서 말할 수 있는 수준이 기준 — 짧게가 아니라 이해되게.

## Workflow

1. `yt.py`로 가져온다(형식 요청은 `--prompt`).
2. 결과를 검증한다 — 영상에 없는 내용이 섞이지 않았는지, 타임스탬프가 그럴듯한지. 의심되면 `--prompt "N분 구간에서 실제로 뭐라고 말했는지 인용"`으로 재확인.
3. 유저 요청 형식으로 다듬어 전달. 출력의 "[모델 · tokens]" 꼬리(stderr)는 붙이지 않는다.

## Error Handling

- **HTTP 400**: 비공개·연령제한·삭제 영상 또는 URL 형식 — 유저에게 URL 확인 요청.
- **HTTP 429**: 무료 쿼터(분당/일일) — 잠시 후 재시도 또는 `--fast`.
- **키 없음(exit 3)**: 유저에게 `GEMINI_API_KEY` 등록을 안내(키를 채팅으로 받지 말 것).
- **`[gemini 영상 모드 실패 → apify]` / `[apify 불가: …]`**(stderr): 정상적인 폴백 진행. 재시도하지 않는다.
- **자막 API IP 차단**(`RequestBlocked`/`IpBlocked`): 클라우드/VPS IP 차단 상태. residential 프록시 없이 재시도는 의미 없다. 페이지를 열어도 자막 본문은 동적 로드라 건지지 못한다 — 더 시도할 수단이 없으면 "자막 확보 불가"로 보고.
