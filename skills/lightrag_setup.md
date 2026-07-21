# Setting Up LightRAG for Retrieval-Augmented Generation

## Introduction
LightRAG is a lightweight knowledge-graph RAG framework designed for high scalability and performance. This skill covers the steps to set up and deploy LightRAG for efficient management of knowledge graphs and vector embeddings.

## Prerequisites
- Python environment
- uv for package management
- Docker (optional)

## Steps
### Step 1: Install uv and LightRAG
Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` (Unix/macOS) or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows)
Install LightRAG Server using uv: `uv tool install "lightrag-hku[api]"`
### Step 2: Build Front-end Artifacts
- `bun install --frozen-lockfile`
- `bun run build`
### Step 3: Setup Environment File
- Copy `env.example` to `.env`: `cp env.example .env`
- Update `.env` with LLM and embedding configurations
### Step 4: Launch the Server
- `lightrag-server`

## Tools and Concepts
- **uv**: Package manager for Python
- **LightRAG**: Lightweight knowledge-graph RAG framework
- **Docker**: Containerization platform
- **Docker Compose**: Tool for defining and running multi-container Docker applications
- **bun**: Fast, efficient package manager for JavaScript
- **PostgreSQL**: Relational database management system
- **Neo4J**: Graph database management system
- **MinerU**, **Docling**: Document parsing engines
- **Retrieval-Augmented Generation**: Approach to improve generation tasks by augmenting the input with relevant information retrieved from a knowledge base
- **Knowledge Graph**: Graphical representation of knowledge that integrates and links data from various sources
- **Vector Embeddings**: Method of representing words or phrases as vectors in a high-dimensional space
- **Multimodal Document Parsing**: Process of extracting and analyzing data from documents that contain multiple types of media (e.g., text, images, tables)
- **Cross-Modal Entity Mapping**: Technique for mapping entities across different modalities (e.g., from text to images)

## Related Skills
- [lightrag](lightrag)
- [ragflow_self_hosting_guide](ragflow_self_hosting_guide)

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | github_readme |
