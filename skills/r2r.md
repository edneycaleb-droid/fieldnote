# R2R

## Description

SoTA production-ready AI retrieval system. Agentic Retrieval-Augmented Generation (RAG) with a RESTful API.

## Steps

- **📁 Multimodal Ingestion**: Parse `.txt`, `.pdf`, `.json`, `.png`, `.mp3`, and more
- **🔍 Hybrid Search**: Semantic + keyword search with reciprocal rank fusion
- **🔗 Knowledge Graphs**: Automatic entity & relationship extraction
- **🤖 Agentic RAG**: Reasoning agent integrated with retrieval
- **🔐 User & Access Management**: Complete authentication & collection system
- Join our Discord for support and discussion
- Submit feature requests or bug reports
- Open PRs for new features, improvements, or documentation

## Tools

anthropic, docker, openai, artificial-intelligence, large-language-models, python, question-answering, rag, retrieval-augmented-generation, retrieval-systems, search

## Source

GitHub: [SciPhi-AI/R2R](https://github.com/SciPhi-AI/R2R) ⭐ 7,937

## README Excerpt

The most advanced AI retrieval system.

Agentic Retrieval-Augmented Generation (RAG) with a RESTful API.

Docs ·

Report Bug ·

Feature Request ·

Discord

# About
R2R is an advanced AI retrieval system supporting Retrieval-Augmented Generation (RAG) with production-ready features. Built around a RESTful API, R2R offers multimodal content ingestion, hybrid search, knowledge graphs, and comprehensive document management.

R2R also includes a **Deep Research API**, a multi-step reasoning system that fetches relevant data from your knowledgebase and/or the internet to deliver richer, context-aware answers for complex queries.

# Usage

```python
# Basic search
results = client.retrieval.search(query="What is DeepSeek R1?")

# RAG with citations
response = client.retrieval.rag(query="What is DeepSeek R1?")

# Deep Research RAG Agent
response = client.retrieval.agent(

message={"role":"user", "content": "What does deepseek r1 imply? Think about market, societal implications, and more."},

rag_generation_config={

"model": "anthropic/claude-3-7-sonnet-20250219",

"extended_thinking": True,

"thinking_budget": 4096,

"temperature": 1,

"top_p": None,

"max_tokens_to_sample": 16000,

},
)
```

## Getting Started
```bash
# Quick install and run in light mode
pip install r2r
export OPENAI_API_KEY=sk-...
python -m r2r.serve

# Or run in full mode with Docker
# git clone git@github.com:SciPhi-AI/R2R.git && cd R2R
# export R2R_CONFIG_NAME=full OPENAI_API_KEY=sk-...
# docker compose -f compose.full.yaml --profile postgres up -d
```

For detailed self-hosting instructions, see the self-hosting docs.

## Demo
https://github.com/user-attachments/assets/173f7a1f-7c0b-4055-b667-e2cdcf70128b

## Using the API

### 1. Install SDK & Setup

```bash
# Install SDK
pip install r2r  # Python
# or
npm i r2r-js

# JavaScript
```

### 2. Client Initialization

```python
from r2r import R2RClient
client = R2RClient(base_url="http://localhost:7272")
```

```javascript
const { r2rClient } = require

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [SciPhi-AI/R2R](https://github.com/SciPhi-AI/R2R) | github_readme |
