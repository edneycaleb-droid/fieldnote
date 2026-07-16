# ⚡ Fieldnote — Provider Reference

Complete reference for every AI provider, tool, and service used by Fieldnote.
The system is **free-first**: every capability has a free path. Paid providers are optional quality upgrades.

---

## 🆓 Free Providers — no credit card required

### LLM Providers

#### 1. Groq (Primary — fastest, highest quality free tier)
- **Models:** `llama-3.3-70b-versatile`, `gemma2-9b-it`, `mixtral-8x7b-32768`, `llama-3.1-8b-instant`
- **Free tier:** 14,400 tokens/min, 6,000 req/day — no credit card
- **Get key:** https://console.groq.com/keys
- **Secret name:** `GROQ`
- **Role:** Primary extraction (educator + practitioner lens), fallback transcription
- **Free alternative to:** OpenAI GPT-4o-mini, Anthropic Claude

#### 2. Gemini AI Studio (Secondary fallback)
- **Models:** `gemini-2.0-flash`, `gemini-1.5-flash-8b`
- **Free tier:** 1,500 req/day, 1M tokens/min — no credit card
- **Get key:** https://aistudio.google.com/app/apikey ← **use AI Studio, not Cloud Console**
- **Secret name:** `Gemini`
- **⚠️ Important:** Cloud Console keys have zero quota. AI Studio keys work for free.
- **Free alternative to:** OpenAI GPT-4, Anthropic Claude

#### 3. HuggingFace Serverless Inference (Tertiary fallback)
- **Models:** `Qwen/Qwen2.5-72B-Instruct`, `meta-llama/Llama-3.1-8B-Instruct`
- **Free tier:** Anonymous access works, token unlocks higher limits
- **Get token:** https://huggingface.co/settings/tokens (read token, free)
- **Secret name:** `HF_TOKEN`
- **Free alternative to:** OpenAI, Cohere

#### 4. OpenRouter (Quaternary fallback)
- **Models:** `meta-llama/llama-3.2-3b-instruct:free`, `mistralai/mistral-7b-instruct:free`, + 50+ free models
- **Free tier:** Free models available with a free account, no credit card
- **Get key:** https://openrouter.ai/keys
- **Secret name:** `OPENROUTER_API_KEY`
- **Free alternative to:** Any paid LLM API

---

### Transcription

The pipeline tries each method in order and stops at the first success:

#### 1. YouTube Captions (First choice — zero compute)
- **API:** `youtube-transcript-api` (free, no key)
- **Cost:** Free — reads existing captions track directly from YouTube
- **Limitation:** Only works if the video has a captions/subtitles track enabled

#### 2. Groq Whisper (Cloud fallback — free tier)
- **Model:** `whisper-large-v3`
- **Free tier:** ~8 hours audio/day — no credit card
- **Same key as:** `GROQ`
- **Free alternative to:** AssemblyAI, Deepgram, OpenAI Whisper API

#### 3. faster-whisper (Local CPU fallback — always free)
- **Repo:** https://github.com/guillaumekambham/faster-whisper
- **Cost:** Free forever — runs on CPU in Replit
- **Models:** `tiny`, `base`, `small`, `medium`, `large-v3`
- **Free alternative to:** Any paid transcription API
- **Note:** Model cached at `workspace/.cache/fw_models/` — survives restarts

---

### Infrastructure (all free)

| Tool | License | Purpose | Repo |
|------|---------|---------|------|
| **yt-dlp** | Unlicense | YouTube download, metadata, playlist | https://github.com/yt-dlp/yt-dlp |
| **ffmpeg** | LGPL/GPL | Audio extraction, format conversion | https://ffmpeg.org |
| **Flask** | BSD | Web server | https://flask.palletsprojects.com |
| **GitHub API** | — | Repo sync, discovery (5k req/hr with PAT) | https://docs.github.com/en/rest |

---

## 💳 Paid Providers — and their free alternatives

### OpenAI (the only truly paid dependency)
- **Models used:** `gpt-4o-mini`, `gpt-4o`
- **Secret name:** `CHATGPT`
- **Position in fallback chain:** #3 (after Groq and Gemini)
- **When used:** Only when Groq and Gemini are both quota-exhausted
- **✅ Free alternative:** Groq llama-3.3-70b — already wired as provider #1
- **How to avoid paying entirely:** Set only `GROQ` — OpenAI is never called unless you're completely out of free quota

---

## 🔄 Fallback Chain

The provider router tries in this order. **Any provider can be omitted** — the next one takes over automatically.

```
Groq (free)
  → llama-3.3-70b-versatile  [primary model]
  → gemma2-9b-it             [if llama rate-limited]
  → mixtral-8x7b-32768       [if gemma rate-limited]
  → llama-3.1-8b-instant     [smallest, fastest]

Gemini (free AI Studio key)
  → gemini-2.0-flash         [primary]
  → gemini-1.5-flash-8b      [fallback]

OpenAI (paid — only if both above exhausted)
  → gpt-4o-mini              [default]
  → gpt-4o                   [if mini unavailable]

HuggingFace (free)
  → Qwen2.5-72B-Instruct
  → Llama-3.1-8B-Instruct

OpenRouter (free models)
  → llama-3.2-3b-instruct:free
  → mistral-7b-instruct:free
```

**Blackout rules:**
- Rate limit (429) → 30-second backout, then retry next model/provider
- Quota exhausted → 2-hour blackout for that provider
- Auth error → permanent blackout until restart
- No key → silently skipped

---

## 🤖 Free-Alternative Auto-Pairing

When the GitHub Discovery Agent finds a repo that uses a paid service, it automatically:
1. Detects the paid dependency (OpenAI, Pinecone, Cohere, etc.)
2. Searches GitHub for a free equivalent
3. Extracts a skill from the free alternative
4. Links both skills in `assistant_knowledge/discoveries/`

**Covered pairings:**

| Paid Service | Free Alternatives Searched |
|---|---|
| OpenAI / GPT-4 | Groq, Ollama, vLLM, LiteLLM |
| Anthropic Claude | Groq, Ollama, Together AI |
| Pinecone | Chroma, Qdrant, FAISS, LanceDB |
| Weaviate Cloud | Qdrant, Chroma, Milvus |
| Cohere | sentence-transformers, FastEmbed |
| AssemblyAI | faster-whisper, Whisper |
| Deepgram | faster-whisper, Whisper |
| ElevenLabs | Coqui TTS, Piper TTS, Bark |
| Stability AI API | Diffusers, Automatic1111 |
| Replicate | Ollama, Diffusers, ComfyUI |
| Azure OpenAI | LiteLLM, Ollama |
| Mistral API (paid) | Ollama + Mistral, Groq + Mistral |
| Voyage AI | sentence-transformers, Nomic Embed |

---

## 🚀 Quickstart — 100% free setup

```bash
# Minimum viable setup (all free, no credit card):
GROQ=gsk_...          # https://console.groq.com/keys
GITHUBPAT=ghp_...     # https://github.com/settings/tokens

# Recommended additions (all free):
Gemini=AIza...        # https://aistudio.google.com/app/apikey (AI Studio key)
HF_TOKEN=hf_...       # https://huggingface.co/settings/tokens
OPENROUTER_API_KEY=sk-or-... # https://openrouter.ai/keys

# Optional paid upgrade:
CHATGPT=sk-...        # https://platform.openai.com/api-keys (not needed for full functionality)
```

> With just `GROQ` set, Fieldnote runs all extraction, transcription, discovery, and enhancement pipelines at full capability using the free tier.

---

*See the [skill library](README.md) for extracted skills. Auto-maintained by Fieldnote.*
