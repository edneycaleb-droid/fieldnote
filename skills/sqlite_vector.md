# sqlite-vector

## Description

SQLite-Vector is a cross-platform, ultra-efficient SQLite extension that brings vector search capabilities to your embedded database.

## Steps

- **No virtual tables required** – store vectors directly as `BLOB`s in ordinary tables
- **Blazing fast** – optimized C implementation with SIMD acceleration
- **TurboQuant support** – SIMD 2-, 3-, and 4-bit quantization scans with `qtype=TURBO`
- **Low memory footprint** – defaults to just 30MB of RAM usage
- **Zero preindexing needed** – no long preprocessing or index-building phases
- **Works offline** – perfect for on-device, privacy-preserving AI workloads
- **Plug-and-play** – drop into existing SQLite workflows with minimal effort
- **Cross-platform** – works out of the box on all major OSes

## Tools

redis, weaviate, faiss, sqlite, C

## Source

GitHub: [sqliteai/sqlite-vector](https://github.com/sqliteai/sqlite-vector) ⭐ 1,030

## README Excerpt

SQLite-Vector

Production-grade vector search inside SQLite.

Exact search, SIMD distance kernels, and SIMD 2/3/4-bit TurboQuant scans — runs anywhere SQLite runs: mobile, browser, edge, server.

Free managed instance → ·

Docs ·

Website ·

Blog

Data:

Vector ·

Sync ·

Columnar ·

JS

AI:

AI ·

Agent ·

Memory ·

MCP

> **Building RAG or semantic search?** SQLite-Vector ships as an extension you can drop into any SQLite app. Need it managed with sync and auth? **SQLite Cloud free tier** gives you 512 MB and 20 connections, no credit card.

---

# SQLite Vector

**SQLite Vector** is a cross-platform, ultra-efficient SQLite extension that brings vector search capabilities to your embedded database. It works seamlessly on **iOS, Android, Windows, Linux, and macOS**, using just **30MB of memory** by default. With support for **Float32, Float16, BFloat16, Int8, UInt8, 1Bit, and TurboQuant 2/3/4-bit quantization**, plus **highly optimized distance functions**, it's the ideal solution for **Edge AI** applications.

SQLite-Vector includes **TurboQuant**, a compact data-oblivious vector quantizer inspired by the Google Research paper TurboQuant: Online Vector Quantization with Near-Optimal Distortion Rate. It stores each vector as low-bit scalar codes plus one scale value, then scores directly from SIMD lookup-table kernels without reconstructing full vectors.

## Highlights

* **No virtual tables required** – store vectors directly as `BLOB`s in ordinary tables
* **Blazing fast** – optimized C implementation with SIMD acceleration
* **TurboQuant support** – SIMD 2-, 3-, and 4-bit quantization scans with `qtype=TURBO`
* **Low memory footprint** – defaults to just 30MB of RAM usage
* **Zero preindexing needed** – no long preprocessing or index-building phases
* **Works offline** – perfect for on-device, privacy-preserving AI workloads
* **Plug-and-play** – drop into existing SQLite workflows with minimal effort
* **Cross-platform** – works out of the box on all major OSes

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [sqliteai/sqlite-vector](https://github.com/sqliteai/sqlite-vector) | github_readme |
