# Self-Hosting RAGFlow for Enhanced LLM Context

## Description
Retrieval Augmented Generation (RAG) is a technique that combines a retriever model with a generator model to produce more accurate and informative text. RAGFlow is an open-source RAG engine that enables developers to build superior context layers for Large Language Models (LLMs). This skill provides a comprehensive guide to self-hosting RAGFlow on your own infrastructure, allowing you to deploy a powerful context layer for LLMs.

## Prerequisites

Before starting, ensure your system meets the following requirements:

*   **CPU**: >= 4 cores
*   **RAM**: >= 16 GB
*   **Disk**: >= 50 GB
*   **Docker**: >= 24.0.0
*   **Docker Compose**: >= v2.26.1
*   **Python**: >= 3.13
*   **gVisor**: Install if using the code executor sandbox.

## System Configuration

*   Verify and set `vm.max_map_count` to at least 262144 using `sysctl -w vm.max_map_count=262144`. Persist this change in `/etc/sysctl.conf`.

## Installation and Setup

1.  **Clone the RAGFlow repository**:
    ```bash
    git clone https://github.com/infiniflow/ragflow.git
    ```
2.  **Navigate to the docker directory**:
    ```bash
    cd ragflow/docker
    ```
3.  **Checkout a specific version** (optional, e.g., `git checkout v0.26.4`).
4.  **Configure the system**:
    *   Edit `.env` and `service_conf.yaml.template` files as needed.
    *   To enable GPU acceleration, add or modify the `DEVICE=gpu` line in the `.env` file before launching.

## Launching RAGFlow

1.  **Start the server using Docker Compose**:
    ```bash
    docker compose -f docker-compose.yml up -d
    ```
2.  **Check server status**:
    ```bash
    docker logs -f docker-ragflow-cpu-1
    ```
3.  **Access RAGFlow** in a web browser at `http://IP_OF_YOUR_MACHINE`.

## Advanced Configuration

### Switching Document Engines

To switch the document engine from Elasticsearch to Infinity:

1.  Stop the current containers:
    ```bash
    docker compose -f docker-compose.yml down -v
    ```
2.  Set `DOC_ENGINE=infinity` in the `docker/.env` file.
3.  Restart the containers:
    ```bash
    docker compose -f docker-compose.yml up -d
    ```
    *Note: Infinity on Linux/arm64 is not officially supported.*

### Building a Docker Image

To build a custom Docker image:

1.  Clone the repository:
    ```bash
    git clone https://github.com/infiniflow/ragflow.git
    cd ragflow/
    ```
2.  Build the image (add proxy arguments if needed):
    ```bash
    docker build --platform linux/amd64 -f Dockerfile -t infiniflow/ragflow:nightly .
    ```

## Concepts

*   Retrieval Augmented Generation (RAG)
*   Large Language Models (LLMs)
*   Context Layers
*   Agent-Harness
*   Agentic-AI
*   Agentic-Retrieval
*   Self-Hosting
*   Docker Images
*   Document Engines (Elasticsearch, Infinity)
*   GPU Acceleration

## Tools

*   RAGFlow
*   Docker
*   Docker Compose
*   Elasticsearch
*   MinIO
*   Redis
*   MySQL
*   git
*   bash
*   sed
*   gVisor

## Related Skills

*   ragflow

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [infiniflow/ragflow](https://github.com/infiniflow/ragflow) | github_readme |
