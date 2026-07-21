# pasa

## Description

PaSa -- an advanced paper search agent powered by large language models. It can autonomously make a series of decisions, including invoking search tools, reading papers, and selecting relevant referen

## Steps

- **Google.** Use Google to search the query directly.
- **Google Scholar.** Queries are submitted directly to Google Scholar.
- **Google with GPT-4o.** We first employ GPT-4o to paraphrase the scholar query. The paraphrased query is then searched o
- **ChatGPT.** We submit the scholar query to ChatGPT, powered by search-enabled GPT-4o. Due to the need for manual query
- **GPT-o1.** Prompt GPT-o1 to process the scholar query.
- **PaSa-GPT-4o.** Prompt GPT-4o within the PaSa framework. It can perform multiple searches, paper reading, and citation
- The `crawler` generates the search queries from the user query and choose the expand sections from ll secondary section
- The `selector` takes the title and abstract of the paper as input and generates a score which indicates the relevance be

## Tools

transformers, huggingface, research, Python

## Source

GitHub: [bytedance/pasa](https://github.com/bytedance/pasa) ⭐ 1,625

## README Excerpt

# PaSa: An LLM Agent for Comprehensive Academic Paper SearchACL 2025 (Main)

ByteDance Seed

[](https://arxiv.org/abs/2501.10120)
[](https://pasa-agent.ai)
[](https://huggingface.co/bytedance-research/pasa-7b-crawler)
[](https://huggingface.co/bytedance-research/pasa-7b-selector)
[](https://huggingface.co/datasets/CarlanLark/pasa-dataset)

## Introduction

We introduce PaSa, an advanced **Pa**per **S**e**a**rch agent powered by large language models. PaSa can autonomously make a series of decisions, including invoking search tools, reading papers, and selecting relevant references, to ultimately obtain comprehensive and accurate results for complex scholarly queries. We optimize PaSa using reinforcement learning with a synthetic dataset, AutoScholarQuery, which includes 35k fine-grained academic queries and corresponding papers sourced from top-tier AI conference publications. Additionally, we develop RealScholarQuery, a benchmark collecting real-world academic queries to assess PaSa performance in more realistic scenarios. Despite being trained on synthetic data, PaSa significantly outperforms existing baselines on RealScholarQuery, including Google, Google Scholar, Google with GPT-4 for paraphrased queries, chatGPT (search-enabled GPT-4o), GPT-o1, and PaSa-GPT-4o (PaSa implemented by prompting GPT-4o). Notably, PaSa-7B surpasses the best Google-based baseline, Google with GPT-4o, by 37.78% in recall@20 and 39.90% in recall@50. It also exceeds PaSa-GPT-4o by 30.36% in recall and 4.25% in precision.

## Quick Start

You can prepare a detailed description of your academic search needs, and search for papers on https://pasa-agent.ai

[](https://www.youtube.com/watch?v=LhXCKZyriNs)

## Architecture

The PaSa system consists of two LLM agents, Crawler and Selector. The Crawler processes the user query and can access papers from the paper queue. It can autonomously invoke the search tool, expand citations, or stop processing of the current paper. All papers collected by

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [bytedance/pasa](https://github.com/bytedance/pasa) | github_readme |
