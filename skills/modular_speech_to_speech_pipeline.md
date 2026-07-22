# Modular Speech-to-Speech Agent Pipeline with Hugging Face

This skill outlines the architecture and implementation of a flexible, low-latency speech-to-speech pipeline designed for building voice agents. The core of the system is a modular, four-stage cascade: Voice Activity Detection (VAD), Speech-to-Text (STT), Language Model (LLM), and Text-to-Speech (TTS). Each stage is implemented as a separate thread and connected via queues, allowing for interchangeable backends and easy customization.

The pipeline is exposed through an OpenAI Realtime-compatible WebSocket API, enabling seamless integration with various clients. This guide provides a step-by-step approach to setting up and configuring this pipeline using the `speech-to-speech` library.

## Key Features:

*   **Modular Architecture:** Easily swap components (VAD, STT, LLM, TTS) with different backends.
*   **Low-Latency:** Optimized for real-time performance.
*   **OpenAI Realtime API Compatibility:** Seamless integration with compatible clients.
*   **Flexible Configuration:** Supports various run modes and backend options.

## Setup and Configuration:

1.  **Installation:**
    *   Install the `speech-to-speech` Python package using pip: `pip install speech-to-speech`.
    *   Alternatively, clone the repository from GitHub and install in editable mode for development: `uv sync`.

2.  **Core Components:** Understand the four-component pipeline: VAD, STT, LLM, TTS, connected by queues.

3.  **Component Selection:**
    *   **STT Backends:** Choose from options like Parakeet TDT, Faster Whisper, or MLX Whisper (`whisper-mlx`).
    *   **TTS Backends:** Select from Qwen3-TTS (`qwentts-cpp-python`), Kokoro-82M, Pocket TTS, ChatTTS, or MMS TTS.
    *   **LLM Backends:** Configure to use `responses-api` or `chat-completions` endpoints. You can point to self-hosted servers (using vLLM or llama.cpp) or hosted providers.

4.  **LLM API Key:** If using OpenAI-compatible LLM backends, set the `OPENAI_API_KEY` environment variable.

5.  **Run Modes:**
    *   `realtime`: For OpenAI Realtime-compatible WebSocket API.
    *   `local`: For direct microphone input and speaker output.
    *   `websocket`: For raw PCM audio streaming over WebSocket.
    *   `socket`: For raw PCM audio streaming over TCP sockets.

6.  **Running the Pipeline:** Use the `speech-to-speech` command with desired configurations for VAD, STT, LLM, and TTS components, specifying the run mode.

7.  **Platform-Specific Optimizations:**
    *   **macOS (MLX):** For local LLM inference on macOS, use the `mlx-lm` backend and configure with `--local_mac_optimal_settings`.
    *   **Linux (CUDA):** If using Qwen3-TTS on Linux with CUDA, ensure the correct `qwentts-cpp-python` wheel is installed matching your CUDA version.

8.  **Self-Hosting LLMs:** Optionally, self-host LLM backends using vLLM or llama.cpp servers and point the pipeline to their respective API endpoints.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-22 | [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) | github_readme |
