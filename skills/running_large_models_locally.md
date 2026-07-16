# Efficiently Running Large AI Models on Local Machines

## Introduction
Modern large AI models — particularly mixture-of-experts (MoE) architectures like DeepSeek and Mixtral — can run on consumer hardware with the right tooling. The key techniques are quantisation (shrinking model weights), expert streaming (loading only the active expert sub-networks from SSD), and model offloading (moving layers between RAM and disk on demand). With these approaches a 70B-parameter model can run on a laptop with 16 GB RAM.

## Core Concepts

* **Mixture of experts (MoE)** — Architecture where each forward pass activates only a fraction of the model's "expert" sub-networks. Reduces compute and memory per token without reducing total parameter count.
* **Quantisation** — Reducing weight precision from 32-bit float to 4-bit or 8-bit integers (GGUF formats: Q4_K_M, Q4_K_S, Q8_0). A 70B model at Q4_K_M fits in ~40 GB; smaller quants trade quality for RAM.
* **Expert caching** — Keeping recently-used expert weights in RAM so the next token that needs the same expert avoids a disk read.
* **Expert streaming** — Reading expert weights from NVMe SSD on demand rather than loading the full model into RAM. Colibri implements this for DeepSeek MoE models.
* **Predictive routing** — Pre-loading expert weights the router is likely to select next, hiding SSD latency behind computation.
* **SSD vs RAM tradeoff** — NVMe SSDs (5–7 GB/s sequential) can stream experts fast enough to sustain a few tokens/second even when the model is 10× larger than available RAM.

## Steps

1. **Choose a model format** — download GGUF-quantised models from Hugging Face:
   ```bash
   pip install huggingface_hub
   huggingface-cli download bartowski/Llama-3.3-70B-Instruct-GGUF \
     --include "Llama-3.3-70B-Instruct-Q4_K_M.gguf" --local-dir ./models
   ```
2. **Install ollama** — easiest path for most models; handles download, quantisation selection, and serving:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull llama3.3                # downloads and runs locally
   ollama run llama3.3                 # interactive chat
   ollama serve                        # starts REST API on :11434
   # Use the OpenAI-compatible endpoint:
   curl http://localhost:11434/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"llama3.3","messages":[{"role":"user","content":"Hello"}]}'
   ```
3. **Install llama.cpp** for fine-grained CPU control:
   ```bash
   git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp
   make -j$(nproc)
   ./llama-cli -m /path/to/model.gguf -n 256 -p "Hello" --threads 8 --ctx-size 4096
   ```
4. **For MoE models with limited RAM — use Colibri** (streams experts off SSD):
   ```bash
   pip install colibri-inference
   colibri serve --model deepseek-r1 --ssd-path /path/to/model/
   ```
5. **Tune threads and context** — set `--threads $(nproc)` and `--ctx-size 4096`; larger contexts use RAM linearly, so reduce if memory is tight.
6. **Monitor resource usage** — use `htop` for RAM pressure and `nvtop` or `nvidia-smi` for VRAM. If RAM is exhausted, switch to a smaller quantisation (Q4_K_S instead of Q4_K_M).
7. **Use vLLM for GPU batch inference** (GPU required; best for serving multiple users):
   ```bash
   pip install vllm
   python -m vllm.entrypoints.openai.api_server \
     --model meta-llama/Llama-3.1-8B-Instruct --port 8000
   ```
8. **Use llamafile for zero-install sharing** — bundles the model and engine into one executable:
   ```bash
   chmod +x mistral-7b-instruct.llamafile && ./mistral-7b-instruct.llamafile
   ```

## Tools

* **ollama** — The easiest way to run local LLMs; handles download, quantisation selection, and an OpenAI-compatible REST API. Supports Llama 3, Mistral, Phi, Gemma, DeepSeek, and more.
* **llama.cpp** — C++ inference engine for GGUF models; runs on CPU without a GPU; highly configurable; the engine powering most local inference tools.
* **Colibri** — Expert-streaming inference engine for MoE models (DeepSeek, Mixtral); enables models much larger than available RAM by streaming from NVMe SSD.
* **vLLM** — High-throughput GPU inference server with OpenAI-compatible API; best for batch workloads with PagedAttention.
* **llamafile** — Single-file executable that bundles a GGUF model and llama.cpp; runs on any platform with no installation.
* **LM Studio** — Desktop GUI for downloading and chatting with local GGUF models; beginner-friendly with a built-in model browser.
* **Hugging Face Hub CLI** — `huggingface-cli download` fetches specific model files including GGUF shards with progress tracking.

## Related Skills
* building_ai_agents
* building_ai_agents_with_langchain

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-15 | [We Just Hit the Local LLM Tipping Point (Colibri)](https://youtu.be/19xCOJxWU0A?is=daU4YDM0FL-5gpsh) | whisper |
