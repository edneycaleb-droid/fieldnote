# Deploying NornicDB

## Introduction
NornicDB is a distributed low-latency graph and vector database designed for AI workloads, supporting temporal MVCC, graph traversal, and vector search. This skill teaches how to deploy NornicDB for various use cases, including graph-native retrieval, hybrid search, and canonical truth modeling.

## Deployment Options
NornicDB can be deployed using Docker with various hardware acceleration options (Metal, CUDA, Vulkan) or built from source using Go.

### Docker Deployment
To deploy NornicDB using Docker, run the following command:
```bash
docker run -d --name nornicdb -p 7474:7474 -p 7687:7687 -v nornicdb-data:/data timothyswt/nornicdb-arm64-metal-bge:latest
```

### Building from Source
To build NornicDB from source, clone the repository and run the following command:
```bash
git clone https://github.com/orneryd/NornicDB.git
```
Then build and run NornicDB using:
```bash
go build -o nornicdb ./cmd/nornicdb
./nornicdb serve
```

## Connecting to NornicDB
NornicDB can be connected to using Neo4j drivers and Bolt/Cypher. For example, in Python:
```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7687")
with driver.session() as session:
    session.run("CREATE (n:Memory {content: 'Hello NornicDB'})")
```

## Features and Benefits
NornicDB offers several features and benefits, including retention policies for data management, graph + vector retrieval for AI workloads, canonical truth modeling for data consistency, and support for various hardware acceleration options.

## Conclusion
NornicDB is a powerful graph and vector database designed for AI workloads, and this skill provides a comprehensive guide to deploying and utilizing it.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [orneryd/NornicDB](https://github.com/orneryd/NornicDB) | github_readme |
