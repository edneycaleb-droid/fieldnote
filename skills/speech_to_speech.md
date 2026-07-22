# speech-to-speech

## Description

Build local voice agents with open-source models

## Steps

- How it works
- Installation
- Supported components
- Realtime API
- LLM backends
- Multi-language support
- Pocket TTS
- CLI reference

## Tools

vllm, transformers, numpy, huggingface, docker, openai, assistant, language-model, machine-learning, python, speech, speech-synthesis

## Source

GitHub: [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) ⭐ 6,253

## README Excerpt

&nbsp;

# Speech To Speech: Build voice agents with open-source models

[](https://pypi.org/project/speech-to-speech/)
[](https://pypi.org/project/speech-to-speech/)
[](./LICENSE)

A low-latency, fully modular voice-agent pipeline: **VAD -> STT -> LLM -> TTS**, exposed through an **OpenAI Realtime-compatible WebSocket API**. Every component is swappable. The LLM slot speaks OpenAI-compatible protocols, so you can point it at a hosted provider, at HF Inference Providers, or at a vLLM or llama.cpp server on your own hardware for a fully local, fully open stack.

This pipeline runs in production as the conversation backend for thousands of Reachy Mini robots.

## Quickstart

```bash
pip install speech-to-speech
export OPENAI_API_KEY=...
speech-to-speech
```

This starts an OpenAI Realtime-compatible server at `ws://localhost:8765/v1/realtime` using Parakeet TDT for local STT, an OpenAI-compatible LLM, and Qwen3-TTS for local speech output.

From a source checkout, talk to it from a second terminal:

```bash
python scripts/listen_and_play_realtime.py --host 127.0.0.1 --port 8765
```

Prefer to keep the LLM on your own machine? Serve Gemma 4 with llama.cpp:

```bash
llama-server -hf ggml-org/gemma-4-E4B-it-GGUF -np 2 -c 65536 -fa on --swa-full
```

Then point the OpenAI-compatible LLM backend at it:

```bash
speech-to-speech \

--model_name "ggml-org/gemma-4-E4B-it-GGUF" \

--responses_api_base_url "http://127.0.0.1:8080/v1" \

--responses_api_api_key ""
```

Any OpenAI Realtime-compatible client can connect. See Realtime API for the protocol and LLM backends for provider and local-server options.

## Index

* How it works
* Installation
* Supported components
* Run modes
* Realtime API
* LLM backends
* Multi-language support
* Pocket TTS
* CLI reference
* Contributing
* Star history
* Citations

## How it works

The pipeline is a cascade of four components, each running in its own thread and connected by queues:

1. **Voice Activity Detection (VAD)**: Silero VAD v5 dete

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-22 | [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) | github_readme |
