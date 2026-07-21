# graphrag

## Description

A modular graph-based Retrieval-Augmented Generation (RAG) system

## Steps

- To learn about our contribution guidelines, see CONTRIBUTING.md
- To start developing _GraphRAG_, see DEVELOPING.md
- Join the conversation and provide feedback in the GitHub Discussions tab!
- What is GraphRAG?
- What can GraphRAG do?
- What are GraphRAG’s intended use(s)?
- How was GraphRAG evaluated? What metrics are used to measure performance?
- What are the limitations of GraphRAG? How can users minimize the impact of GraphRAG’s limitations when using the system?

## Tools

gpt, gpt-4, gpt4, graphrag, llm, llms, rag, Python

## Source

GitHub: [microsoft/graphrag](https://github.com/microsoft/graphrag) ⭐ 34,698

## README Excerpt

# GraphRAG

👉 Microsoft Research Blog Post
👉 Read the docs
👉 GraphRAG Arxiv

## Overview

The GraphRAG project is a data pipeline and transformation suite that is designed to extract meaningful, structured data from unstructured text using the power of LLMs.

To learn more about GraphRAG and how it can be used to enhance your LLM's ability to reason about your private data, please visit the Microsoft Research Blog Post.

## Quickstart

To get started with the GraphRAG system we recommend trying the command line quickstart.

## Repository Guidance

This repository presents a methodology for using knowledge graph memory structures to enhance LLM outputs. Please note that the provided code serves as a demonstration and is not an officially supported Microsoft offering.

⚠️ *Warning: GraphRAG indexing can be an expensive operation, please read all of the documentation to understand the process and costs involved, and start small.*

## Diving Deeper

- To learn about our contribution guidelines, see CONTRIBUTING.md
- To start developing _GraphRAG_, see DEVELOPING.md
- Join the conversation and provide feedback in the GitHub Discussions tab!

## Prompt Tuning

Using _GraphRAG_ with your data out of the box may not yield the best possible results.
We strongly recommend to fine-tune your prompts following the Prompt Tuning Guide in our documentation.

## Versioning

Please see the breaking changes document for notes on our approach to versioning the project.

*Always run `graphrag init --root [path] --force` between minor version bumps to ensure you have the latest config format. Run the provided migration notebook between major version bumps if you want to avoid re-indexing prior datasets. Note that this will overwrite your configuration and prompts, so backup if necessary.*

## Responsible AI FAQ

See RAI_TRANSPARENCY.md

- What is GraphRAG?
- What can GraphRAG do?
- What are GraphRAG’s intended use(s)?
- How was GraphRAG evaluated? What metrics are used to measure perfor

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [microsoft/graphrag](https://github.com/microsoft/graphrag) | github_readme |
