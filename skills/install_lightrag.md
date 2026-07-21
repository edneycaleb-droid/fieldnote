# Install LightRAG with uv or pip for Knowledge-Graph and RAG Development

## Description
LightRAG is a lightweight knowledge-graph RAG framework that addresses key challenges in large-scale graph indexing and retrieval. It captures complex semantic dependencies between entities, enabling deep contextual understanding and exceptional comprehensiveness. This skill covers the installation of LightRAG using uv, pip, or Docker Compose for knowledge graph and RAG development.

## Steps
### Using uv
Use the uv package manager for fast and reliable installation: run `curl -LsSf https://astral.sh/uv/install.sh | sh` for Unix/macOS or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` for Windows

### Installing LightRAG from PyPI
Install LightRAG from PyPI using uv: run `uv tool install "lightrag-hku[api]"`

### Set up the LightRAG server
Set up the LightRAG server using the provided installation instructions.

### Creating a .env file
Create a .env file for LightRAG by running `make env-base`.

### Optional: Using the interactive setup tool
Optional: Use the interactive setup tool with `make env-base-rewrite`.

### Installing LightRAG using uv
Install LightRAG using uv for fast and reliable Python package management.

### Configuring the .env file
Configure the .env file with your LLM and embedding configurations.

## Tools
* uv: Fast and reliable Python package management.
* pip: Python package manager.
* Docker Compose: Containerization tool.
* spaCy: Natural language processing library.

## Concepts
* Knowledge Graphs: Graphs that represent complex relationships between entities.
* RAG Frameworks: Frameworks that enable retrieval-augmented generation.
* Deep Contextual Understanding: The ability to capture complex semantic dependencies between entities.
* Knowledge graph: Graphs that represent complex relationships between entities.
* uv package manager: Fast and reliable package manager.

## Related Skills
None.

## Tags
* rag: Retrieval-augmented generation.
* knowledge-graph: Graphs that represent complex relationships between entities.
* natural-language-processing: Natural language processing library.
* lightrag: LightRAG framework.
* rag-framework: Frameworks that enable retrieval-augmented generation.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | github_readme |
