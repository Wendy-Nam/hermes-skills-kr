# hermes-skills-kr

한국어 사용자를 위한 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 스킬 모음입니다.
제 서버에서 매일 쓰면서 다듬은 것만 올립니다.

| 스킬 | 하는 일 | 필요한 키 |
|---|---|---|
| [`youtube-summary`](skills/youtube-summary) | 유튜브 링크를 한국어로 요약·질문답·챕터·스레드로 정리. Gemini가 영상을 직접 보므로 VPS에서 자막이 막혀도 동작 | `GEMINI_API_KEY` ([무료 발급](https://aistudio.google.com/apikey)) |

구직 자동화는 볼트 템플릿까지 포함된 별도 키트로 있습니다 → [hermes-job-hunt-for-korean](https://github.com/Wendy-Nam/hermes-job-hunt-for-korean)

## 설치

### 스킬 하나만 (추천)

이 레포를 Hermes의 스킬 출처(tap)로 한 번 등록하고, 원하는 스킬만 설치합니다. 스크립트까지 폴더째 설치됩니다.

```bash
hermes skills tap add Wendy-Nam/hermes-skills-kr
```

```bash
hermes skills install youtube-summary
```

설치 후 새 대화부터 적용됩니다. 업데이트는 `hermes skills update`.

### 직접 복사

tap을 쓰지 않거나 Claude Code 같은 다른 에이전트에서 쓸 때는 `skills/<스킬명>` 폴더를 통째로 스킬 폴더에 복사하면 됩니다.

- Hermes (Docker): `/opt/data/skills/<카테고리>/<스킬명>/`
- Hermes (일반 설치): `~/.hermes/skills/<카테고리>/<스킬명>/`
- Claude Code: `~/.claude/skills/<스킬명>/`

## 키 넣기

키는 채팅창에 붙여넣지 마세요. Hermes의 `.env`(Docker: `/opt/data/.env`, 일반 설치: `~/.hermes/.env`)에 한 줄 추가하면 스크립트가 바로 읽습니다.

```
GEMINI_API_KEY=발급받은키
```

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

네트워크 없이 도는 검사만 들어 있습니다(URL 검증, 키 탐색 순서, 키가 없을 때 정직하게 실패하는지).

## 라이선스

MIT
