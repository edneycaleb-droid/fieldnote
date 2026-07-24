# litellm

## Description

The fastest, litest AI Gateway. Rust core with Python SDK. Call 100+ LLM APIs in OpenAI (or native) format with cost tracking, guardrails, load balancing, and logging [Bedrock, Azure, OpenAI, Anthropi

## Steps

- **Unified API** — one interface for 100+ LLMs, no provider-specific SDK juggling
- **Drop-in OpenAI compatibility** — swap providers without rewriting your code
- **Production-ready gateway** — virtual keys, spend tracking, guardrails, load balancing, and an admin dashboard out of t
- **8ms P95 latency** at 1k RPS (benchmarks)

## Tools

gemini, vllm, terraform, langgraph, huggingface, ollama, groq, anthropic, pydantic, openai, ai-gateway, azure-openai

## Source

GitHub: [BerriAI/litellm](https://github.com/BerriAI/litellm) ⭐ 54,517

## README Excerpt

🚅 LiteLLM

LiteLLM AI Gateway

Open Source AI Gateway for 100+ LLMs. Self-hosted. Enterprise-ready. Call any LLM in OpenAI format.

<a href="https://ssh.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https%3A%2F%2Fgithub.com%2FBerriAI%2Flitellm&cloudshell_workspace=terraform%2Flitellm%2Fgcp%2Fexamples%2Fdefault&cloudshell_tutorial=TUTORIAL.md&cloudshell_image=gcr.io/ds-artifacts-cloudshell/deploystack_custom_image&shellonly=true" target="_blank" rel="nofollow">

LiteLLM Proxy Server (AI Gateway) |  Hosted Proxy | Enterprise Tier | Website

---

## What is LiteLLM

LiteLLM is an open source AI Gateway that gives you a single, unified interface to call 100+ LLM providers — OpenAI, Anthropic, Gemini, Bedrock, Azure, and more — using the OpenAI format.

Use it as a **Python SDK** for direct library integration, or deploy the **AI Gateway (Proxy Server)** as a centralized service for your team or organization.

**Jump to LiteLLM Proxy (LLM Gateway) Docs** 
**Jump to Supported LLM Providers**

---

## Why LiteLLM

Managing LLM calls across providers gets complicated fast — different SDKs, auth patterns, request formats, and error types for every model. LiteLLM removes that friction:

- **Unified API** — one interface for 100+ LLMs, no provider-specific SDK juggling
- **Drop-in OpenAI compatibility** — swap providers without rewriting your code
- **Production-ready gateway** — virtual keys, spend tracking, guardrails, load balancing, and an admin dashboard out of the box
- **8ms P95 latency** at 1k RPS (benchmarks)

### OSS Adopters

Netflix

---

## Features

LLMs - Call 100+ LLMs (Python SDK + AI Gateway)

**All Supported Endpoints** - `/chat/completions`, `/responses`, `/embeddings`, `/images`, `/audio`, `/batches`, `/rerank`, `/a2a`, `/messages` and more.

### Python SDK

```shell
uv add litellm
```

```python
from litellm import completion
import os

os.environ["OPENAI_API_KEY"] = "your-openai-key"
os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-key"

# Open

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [BerriAI/litellm](https://github.com/BerriAI/litellm) | github_readme |
