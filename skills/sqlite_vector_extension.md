# SQLite-Vector Extension for Embedded Vector Search

This skill covers the integration and usage of the SQLite-Vector extension, a powerful tool for embedding vector search capabilities directly within SQLite databases. It allows developers to perform efficient, on-device, and offline AI workloads by storing and querying vector embeddings within standard SQLite tables, eliminating the need for external vector databases or complex indexing.

## Overview
The SQLite Vector extension provides a fast, efficient, and scalable solution for vector similarity search in edge and mobile applications. It allows you to integrate vector search capabilities into your SQLite database using a simple and intuitive API.

## Installation and Loading
Download pre-built binaries for your platform (Linux, macOS, Windows, Android, iOS) or the WASM version. Load the extension into your SQLite database using the SQLite CLI with `.load ./vector` or `SELECT load_extension('./vector');`. Alternatively, you can embed the extension directly into your application. For Python projects, the `sqliteai-vector` package can be used.

## Creating and Populating Vector Tables
Create a regular SQLite table with a BLOB column to store your vector embeddings. Insert vectors into this BLOB column, either directly or using helper functions like `vector_as_f32()`.

## Initializing and Quantizing the Vector Index
Initialize the vector extension for a specific table and column using the `vector_init()` function, specifying the vector type and dimensions. For better performance and reduced storage, optionally quantize vectors using `vector_quantize()` with options like `qtype=TURBO` and `qbits`. You can further speed up scans by optionally preloading quantized vectors into memory using `vector_quantize_preload()`.

## Running Nearest Neighbor Queries
Perform nearest neighbor searches using `vector_quantize_scan()`. This function can be joined with your table, accepting a query vector and the desired number of results (k). Utilize streaming mode for progressive results and apply standard SQL filters directly within your queries.

## Example Use Cases
The SQLite Vector extension is ideal for edge and mobile applications where vector similarity search is required. It provides a fast and efficient solution for use cases such as image search, recommendation systems, and natural language processing, enabling robust offline AI capabilities.

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [sqliteai/sqlite-vector](https://github.com/sqliteai/sqlite-vector) | github_readme |
