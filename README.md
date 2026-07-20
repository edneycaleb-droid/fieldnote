# ⚡ Fieldnote

> A personal AI skill library — every YouTube video I learn from becomes a structured, searchable skill.
> **4 skills** · Last synced: 2026-07-20 02:41 UTC

---

## 📚 Skills

| Skill | Description | Tools | Tags |
|-------|-------------|-------|------|
| [The 15 Most INSANE Things Created by KIMI K3 ( KIMI K3 Use Cases)](skills/the_15_most_insane_things_created_by_kimi_k3_kimi_.md) | By TheAIGRID. Key tools: Claude. (Auto-extracted — pending AI enhancement.) | `Claude` | `know` `course` `game` |
| [New Claude Opus 5 LEAKS!](skills/new_claude_opus_5_leaks.md) | By Julian Goldie SEO. Key tools: Claude, Anthropic. (Auto-extracted — pending AI | `Claude` `Anthropic` | `opus` `model` `profit` |
| [Kimi K3 Is NOT the Story. China's AI Master Plan Is](skills/kimi_k3_is_not_the_story_china_s_ai_master_plan_is.md) | By Kyle Balmer \| AI with Kyle. Key tools: Claude, Anthropic. (Auto-extracted — p | `Claude` `Anthropic` | `very` `about` `models` |
| [Run Kimi K3 Inside Claude Code (MAX POWER)](skills/run_kimi_k3_inside_claude_code_max_power.md) | By Superbash (BoxminingAI). Key tools: Claude, anthropic. (Auto-extracted — pend | `Claude` `anthropic` | `code` `kimmy` `cloud` |

---

## 🆓 Free Stack — runs entirely without spending money

Every component has a free path. The system is **free-first by design** — paid providers are optional quality upgrades, never requirements.

### LLM (Language Models)

| Provider | Model | Free Tier | Role in Fieldnote |
|----------|-------|-----------|-------------------|
| **[Groq](https://console.groq.com)** | `llama-3.3-70b-versatile` · `gemma2-9b-it` · `mixtral-8x7b` | 14,400 tokens/min — no card | **Primary** — educator + practitioner extraction |
| **[Gemini AI Studio](https://aistudio.google.com/app/apikey)** | `gemini-2.0-flash` · `gemini-1.5-flash` | 1,500 req/day — no card | Fallback #2 |
| **[HuggingFace](https://huggingface.co/settings/tokens)** | `Qwen/Qwen2.5-72B` · serverless | Anonymous OK, token recommended | Fallback #3 |
| **[OpenRouter](https://openrouter.ai/keys)** | `llama-3.2-3b-instruct:free` + others | Free models, free account | Fallback #4 |

> **To run 100% free:** set only the `GROQ` secret. The router auto-falls-back through all free providers.

### Transcription

| Tool | Type | Cost | Notes |
|------|------|------|-------|
| **YouTube captions** | API | Free | First choice — instant, no compute |
| **[Groq Whisper](https://console.groq.com)** | Cloud API | Free tier (8h audio/day) | Used when captions unavailable |
| **[faster-whisper](https://github.com/guillaumekambham/faster-whisper)** | Local / self-hosted | Free forever | CPU fallback, runs on Replit |

### Infrastructure

| Tool | Cost | Purpose |
|------|------|---------|
| **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** | Free / open source | YouTube download & metadata |
| **[ffmpeg](https://ffmpeg.org)** | Free / open source | Audio extraction & conversion |
| **[GitHub API](https://docs.github.com/en/rest)** | Free (5,000 req/hr with PAT) | Repo sync + discovery |
| **[Flask](https://flask.palletsprojects.com)** | Free / open source | Web server |
| **[Chroma](https://github.com/chroma-core/chroma)** | Free / open source | Free vector DB alternative to Pinecone |
| **[FAISS](https://github.com/facebookresearch/faiss)** | Free / open source | Free vector similarity (Facebook) |
| **[Qdrant](https://qdrant.tech)** | Free self-hosted | Free vector DB alternative to Weaviate |
| **[Ollama](https://github.com/ollama/ollama)** | Free / open source | Free local LLM alternative to OpenAI |
| **[LiteLLM](https://github.com/BerriAI/litellm)** | Free / open source | Free OpenAI-compatible proxy |
| **[sentence-transformers](https://github.com/UKPLab/sentence-transformers)** | Free / open source | Free embeddings alternative to Cohere |

---

## 💳 Paid (optional) — and their free alternatives

Everything paid has a drop-in free replacement already wired into the codebase.

| Paid Service | Used For | Free Alternative | Already Implemented? |
|---|---|---|---|
| **OpenAI GPT-4o-mini** | Educator lens in AI Arena | ✅ **Groq llama-3.3-70b** — same extraction quality, faster, free | ✅ Yes — Groq is provider #1 |
| **OpenAI GPT-4o** | Judge synthesis | ✅ **Groq llama-3.3-70b** via provider router | ✅ Yes — auto-fallback |
| **Pinecone** (if added) | Vector search | ✅ **Chroma** or **FAISS** or **Qdrant** (self-hosted) | ✅ Documented + discovery-paired |
| **AssemblyAI** (if added) | Transcription | ✅ **faster-whisper** (local) + **Groq Whisper** | ✅ Yes — already in stack |
| **ElevenLabs** (if added) | Text-to-speech | ✅ **Coqui TTS** or **Piper TTS** (local) | 🔜 Discoverable |
| **Replicate** (if added) | Image/video AI | ✅ **Diffusers** (local Stable Diffusion) | 🔜 Discoverable |
| **Cohere** (if added) | Embeddings | ✅ **sentence-transformers** (local, CPU) | 🔜 Discoverable |

> **Auto-pairing:** When the GitHub Discovery Agent finds a repo that uses a paid service, it automatically searches for and extracts a free alternative, linking both skills together in the library.

---

## 🤖 How skills are built

Every YouTube URL goes through the **Fieldnote AI Arena**:

| Step | Free Provider | Paid Alternative | Role |
|------|--------------|-----------------|------|
| 1. Transcribe | YouTube captions (instant, free) → Groq Whisper → faster-whisper (local CPU) | — | Text acquisition — captions tried first, Whisper only if captions unavailable |
| 2. Extract A  | Groq llama-3.3-70b | OpenAI GPT-4o-mini | Educator lens — depth & concepts |
| 3. Extract B  | Groq llama-3.3-70b | OpenAI GPT-4o-mini | Practitioner lens — steps & tools |
| 4. Discover   | GitHub API (free) | — | Real repos using these tools |
| 5. Judge      | Groq llama-3.3-70b | OpenAI GPT-4o-mini | Synthesises the best result |
| 6. Sync       | GitHub (free PAT) | — | Pushes here automatically |

Each skill contains: structured steps, tools, concepts, tags, source attribution, related skills, and Python packages.

---

## ⚙️ Autonomous Agents (always free)

| Agent | Schedule | What it does |
|-------|----------|-------------|
| **GitHub Discovery** | Every 2h | Searches GitHub for high-quality repos, extracts skills from READMEs |
| **Free-Alt Pairing** | On discovery | When a paid-tool repo is found, automatically finds + extracts a free alternative |
| **DCA Enhancer** | Every 6h | Re-runs extraction on existing skills to improve quality over time |
| **Watchlist Processor** | Every 1h | Processes queued YouTube URLs |
| **Source Sync** | Every 10min | Mirrors source code changes to this repo (fast path; also runs on every file save) |
| **Full Library Sync** | Every 24h | Full push of all skills, README, and brain graph |
| **Integration Agent** | Every 30min | Health-checks all providers, auto-detects new Replit Secrets, suggests complementary integrations |

---

See [PROVIDERS.md](PROVIDERS.md) for the complete provider reference, rate limits, and setup guide.

*Auto-generated — do not edit directly.*
