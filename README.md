# 🧠 Fieldnote Skill Library

> Everything I learn from YouTube — auto-extracted and synced by AI.
> **1 skill** · Last synced: 2026-07-15 17:13 UTC

---

## 📚 Skills

| Skill | Description | Tools | Tags |
|-------|-------------|-------|------|
| [AI Arena Test Skill](skills/ai_arena_test_skill.md) | Live sync verification: confirms skills auto-push to GitHub on every save. | `ChatGPT` `Groq` `GitHub API` | `AI` `sync` `arena` |

---

## 🤖 How skills are built

Every YouTube URL goes through the **Fieldnote AI Arena**:

| Step | Provider | Role |
|------|----------|------|
| 1. Transcribe | Groq Whisper / YouTube captions | Audio → text |
| 2. Extract A  | ChatGPT GPT-4o-mini | Educator lens — depth & concepts |
| 3. Extract B  | Groq llama-3.3-70b  | Practitioner lens — steps & tools |
| 4. Discover   | GitHub API + READMEs | Real repos using these tools |
| 5. Judge      | GPT-4o-mini | Synthesises the best of all three |
| 6. Sync       | GitHub Sync Agent | Pushes here automatically |

Each skill file contains: structured steps, tools, concepts, tags, source attribution, and related skills.

---

*Auto-generated — do not edit directly.*
