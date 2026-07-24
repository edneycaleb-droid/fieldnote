# NornicDB

## Description

Nornicdb is a distributed low-latency, Graph+Vector, Temporal MVCC with all sub-ms HNSW search, graph traversal, and writes. Using Neo4j Bolt/Cypher and qdrant's gRPC means you can switch with no chan

## Steps

- **Neo4j-compatible by default**: Bolt + Cypher support for existing drivers and applications.
- **Built for AI-native workloads**: vector search, memory decay, and auto-relationships are first-class features.
- **Graph, vector, and ledger semantics in one engine**: hybrid retrieval, graph traversal, canonical graph ledger modelin
- **Protocol flexibility without splitting the system**: REST, GraphQL, Bolt/Cypher, Qdrant-compatible gRPC, and additive
- **Hardware-accelerated execution**: Metal/CUDA/Vulkan pathways for high-throughput graph + semantic workloads.
- **Operational flexibility**: full images (models included), BYOM images, and headless API-only deployments.
- **Agent and Graph-RAG systems**: replacing a Neo4j + Qdrant + embeddings stack with a single deployment for task trackin
- **Translation and evaluation workflows**: replacing a document store plus embeddings pipeline with a single deployment f

## Tools

qdrant, docker, bolt, cypher, database, enterprise-solutions, golang, graph-rag, graphql, hnsw, local-llm, mcp-server

## Source

GitHub: [orneryd/NornicDB](https://github.com/orneryd/NornicDB) ⭐ 832

## README Excerpt

NornicDB

Graph, vector, and historical truth in one database

Neo4j-compatible • Hybrid graph + vector retrieval • Historical reads via MVCC

Achieving Psygnosis for AI

Multi-arch support: CPU | CUDA | Metal | Vulkan

Quick Start •

What It Is •

Why NornicDB •

Benchmarks •

Features •

Docs •

Comparison •

Contributors

[](https://oosmetrics.com/repo/orneryd/NornicDB)

## Quick Start

```bash
# Homebrew
brew tap --trust orneryd/nornicdb && brew install nornicdb && brew services start nornicdb

# arm64 / Apple Silicon
docker run -d --name nornicdb -p 7474:7474 -p 7687:7687 -v nornicdb-data:/data timothyswt/nornicdb-arm64-metal-bge:latest

# amd64 / CPU only
docker run -d --name nornicdb -p 7474:7474 -p 7687:7687 -v nornicdb-data:/data timothyswt/nornicdb-amd64-cpu-bge:latest
```

Open http://localhost:7474 for the admin UI. For NVIDIA CUDA hosts, use `timothyswt/nornicdb-amd64-cuda-bge:latest`. For Vulkan hosts, use `timothyswt/nornicdb-amd64-vulkan-bge:latest`.

---

> Note: Docker on macOS does not expose Metal acceleration. The Apple Silicon image still runs, but GPU acceleration on macOS requires a native install from the releases page or a local build.

---

> **Writing queries?** Start with the Hot-Path Cypher Cookbook — proven query shapes that route through the executor's specialized fast paths.
>
> 🤖 **Building with Claude / agents?** The `docs/skills/` directory contains agent-ready skill files for every Cypher surface: query shapes, decay/promotion policies, managed embeddings, vector & hybrid search, and RAG procedures. Drop them into `.claude/skills/` to make agents fluent in NornicDB.

## What NornicDB Is

NornicDB is a graph database for workloads that need graph traversal, vector retrieval, and historical truth in the same system. It speaks Neo4j's language through Bolt and Cypher, exposes REST, GraphQL, and gRPC interfaces, and can preserve Qdrant-style client workflows where that helps migration.

The architecture draws from research in Tempora

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [orneryd/NornicDB](https://github.com/orneryd/NornicDB) | github_readme |
