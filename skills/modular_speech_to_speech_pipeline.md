# Modular Speech-to-Speech Agent Pipeline with Hugging Face

This skill outlines the architecture and usage of the `speech-to-speech` library, a powerful tool for building highly customizable, low-latency voice agent pipelines. It emphasizes a modular design where each core component—Voice Activity Detection (VAD), Speech-to-Text (STT), Language Model (LLM), and Text-to-Speech (TTS)—can be independently swapped with various open-source backends, enabling seamless integration with existing clients via an OpenAI Realtime-compatible WebSocket API.

## Key Features

*   **Modularity**: Easily interchange components (VAD, STT, LLM, TTS) to suit specific needs and hardware.
*   **Low Latency**: Optimized for real-time interaction.
*   **Open-Source Focus**: Leverages a wide array of open-source models and frameworks.
*   **Flexible Deployment**: Supports local inference, self-hosted servers, and cloud providers.
*   **OpenAI Realtime API Compatibility**: Exposes a WebSocket API compatible with OpenAI's realtime protocol for easy integration with clients.
*   **Extensible Backends**: Supports various backends for each component and allows installation via pip extras for specific models.

## Setup and Configuration

1.  **Installation**: Install the `speech-to-speech` Python package using pip:
    ```bash
    pip install speech-to-speech
    ```
    For development, you can clone the repository and install from source.

2.  **Environment Variables**: If using OpenAI-compatible LLM backends, set the `OPENAI_API_KEY` environment variable.

3.  **Component Configuration**: Configure specific components using CLI flags when running the pipeline:
    *   `--stt`: Specify the Speech-to-Text backend.
    *   `--llm_backend`: Specify the LLM backend.
    *   `--tts`: Specify the Text-to-Speech backend.

4.  **Backend Integration**: 
    *   Select and integrate different backends for VAD, STT, LLM, and TTS based on performance and hardware requirements.
    *   Handle CUDA dependencies for specific TTS backends like Qwen3-TTS by installing compatible wheels (e.g., `pip install qwentts-cpp-python`).
    *   Install optional backends using pip extras (e.g., `pip install speech-to-speech[faster-whisper]`).

5.  **Local LLM Inference**: For local LLM inference, serve models using tools like `llama-cpp-python` or `llama.cpp` and point the pipeline to the local server URL.

## Running the Pipeline

Execute the `speech-to-speech` command-line interface. The default mode uses a WebSocket API for real-time interaction.

*   **Run Modes**: Choose a run mode:
    *   `realtime` (default): WebSocket API for real-time streaming.
    *   `local`: Uses microphone input and system speaker output.
    *   `websocket`: Accepts raw PCM audio over WebSocket.
    *   `socket`: Accepts raw PCM audio over TCP socket.

*   **Client Connections**: Utilize the OpenAI Realtime-compatible WebSocket API for client connections.

## Supported Tools and Models

*   **VAD**: Silero VAD, Parakeet TDT
*   **STT**: Whisper (via `faster-whisper` extra), etc.
*   **LLM**: Local models via `llama.cpp`, `vLLM`, `Transformers`; OpenAI-compatible APIs.
*   **TTS**: Qwen3-TTS, etc.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-22 | [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech) | github_readme |
