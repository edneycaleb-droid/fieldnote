# R2R Agentic Retrieval-Augmented Generation System

## Description
R2R is a state-of-the-art, production-ready AI retrieval system designed for advanced Retrieval-Augmented Generation (RAG) applications. It offers a comprehensive suite of features including a RESTful API, multimodal content ingestion, hybrid search capabilities, knowledge graph integration, and robust document management. A key component is its Deep Research API, which employs multi-step reasoning to fetch relevant data from both internal knowledge bases and the internet, enabling richer, context-aware responses to complex queries.

## Key Features

*   **Agentic RAG**: Integrates a reasoning agent with the retrieval process for more sophisticated questioning and response generation.
*   **Multimodal Ingestion**: Supports ingestion of various file types including .txt, .pdf, .json, .png, and .mp3.
*   **Hybrid Search**: Combines semantic and keyword search for more accurate retrieval.
*   **Knowledge Graphs**: Automatically extracts and utilizes knowledge graphs for enhanced context.
*   **Deep Research API**: Enables complex queries requiring multi-step reasoning and fetching data from internal and external sources.
*   **RESTful API**: Provides a clean API for seamless integration into existing applications.

## Getting Started

### Installation

Install the R2R Python SDK using pip:
```bash
pip install r2r
```

Alternatively, install the JavaScript SDK:
```bash
npm i r2r-js
```

### Initialization

Initialize the R2R client, providing the base URL of your R2R server:
```python
from r2r import R2RClient

client = R2RClient(base_url="http://localhost:7272")
```

### Document Ingestion

Ingest documents using the `client.documents.create()` method. This supports various file types:
```python
client.documents.create(file_path="/path/to/your/document.pdf")
```

### Basic Search

Perform basic semantic searches:
```python
results = client.retrieval.search(query="What is R2R?")
```

### RAG Queries

Execute RAG queries with citations:
```python
results = client.retrieval.rag(query="Explain the RAG system.")
```

### Deep Research Agent

Utilize the Deep Research RAG Agent for complex queries:
```python
results = client.retrieval.agent(user_message="Analyze the impact of X on Y.", rag_generation_config={...})
```

### RAG Generation Configuration

Configure RAG generation parameters for advanced control:
```python
rag_generation_config = {
    "model": "gpt-4o",
    "extended_thinking": True,
    "thinking_budget": 1000,
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens_to_sample": 512
}
```

### Document Management

List ingested documents:
```python
documents = client.documents.list()
```

## Self-Hosting

### Light Mode

Set up R2R in light mode for quick testing:
```bash
pip install r2r
python -m r2r.serve
```

### Full Mode (Docker Compose)

For a full-featured deployment, use Docker Compose:

1.  Clone the R2R repository:
    ```bash
git clone git@github.com:SciPhi-AI/R2R.git
cd R2R
    ```
2.  Set environment variables:
    ```bash
export R2R_CONFIG_NAME=full
export OPENAI_API_KEY=sk-...
    ```
3.  Run Docker Compose:
    ```bash
docker compose -f compose.full.yaml --profile postgres up -d
    ```

## Concepts

*   Retrieval-Augmented Generation (RAG)
*   Agentic RAG
*   Deep Research API
*   Multimodal Ingestion
*   Hybrid Search
*   Knowledge Graphs
*   RESTful API
*   Reciprocal Rank Fusion

## Tools

*   R2R
*   Docker
*   Docker Compose
*   RESTful API
*   OpenAI API

## Python Packages

*   r2r

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [SciPhi-AI/R2R](https://github.com/SciPhi-AI/R2R) | github_readme |
