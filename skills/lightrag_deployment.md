# Deploying LightRAG: A Lightweight, Graph-Based RAG Framework

LightRAG is a lightweight knowledge-graph RAG framework that efficiently indexes and retrieves large-scale graph data, providing exceptional contextual understanding, comprehensiveness, and diversity in query results. It is designed for high scalability and supports seamless incremental knowledge base updates. This skill teaches how to deploy LightRAG using various tools and libraries.

## Steps
- Install uv for fast and reliable Python package management using the command `curl -LsSf https://astral.sh/uv/install.sh | sh` (Unix/macOS) or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows)
- Install LightRAG Server using uv by running `uv tool install "lightrag-hku[api]"`
- Alternatively, install LightRAG Server using pip by running `python -m venv .venv` followed by `pip install "lightrag-hku[api]"`
- Build front-end artifacts by running `cd lightrag_webui` followed by `bun install --frozen-lockfile` and `bun run build`
- Create a .env file with the setup tool
- Setup the .env file using the interactive setup wizard by running `make env-base` followed by `make env-storage` and `make env-server`
- Launch the LightRAG Server with Docker Compose
- Optional: spaCy models for docx smart_heading

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-17 | [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | github_readme |
