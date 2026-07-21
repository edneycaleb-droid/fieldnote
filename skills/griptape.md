# griptape

## Description

Modular Python framework for AI agents and workflows with chain-of-thought reasoning, tools, and memory. 

## Steps

- 🤖 **Agents** consist of a single Task, configured for Agent-specific behavior.
- 🔄 **Pipelines** organize a sequence of Tasks so that the output from one Task may flow into the next.
- 🌐 **Workflows** configure Tasks to operate in parallel.
- 💬 **Conversation Memory** enables LLMs to retain and retrieve information across interactions.
- 🗃️ **Task Memory** keeps large or sensitive Task outputs off the prompt that is sent to the LLM.
- 📊 **Meta Memory** enables passing in additional metadata to the LLM, enhancing the context and relevance of the interact
- 🗣️ **Prompt Drivers**: Manage textual and image interactions with LLMs.
- 🤖 **Assistant Drivers**: Enable interactions with various “assistant” services.

## Tools

fastapi, crewai, pydantic, openai, langchain, anthropic, claude, gpt, huggingface, llm, python

## Source

GitHub: [griptape-ai/griptape](https://github.com/griptape-ai/griptape) ⭐ 2,561

## README Excerpt

[](https://pypi.python.org/pypi/griptape)
[](https://github.com/griptape-ai/griptape/actions/workflows/unit-tests.yml)
[](https://griptape.readthedocs.io/)
[](https://microsoft.github.io/pyright/)
[](https://github.com/astral-sh/ruff)
[](https://codecov.io/github/griptape-ai/griptape)
[](https://discord.gg/griptape)

Griptape is a Python framework designed to simplify the development of generative AI (genAI) applications.
It offers a set of straightforward, flexible abstractions for working with areas such as Large Language Models (LLMs), Retrieval-Augmented Generation (RAG), and much more.

> **Looking for a no-code experience?** Check out Griptape Nodes, a visual desktop application for building and running AI workflows.

## 🛠️ Core Components

### 🏗️ Structures

- 🤖 **Agents** consist of a single Task, configured for Agent-specific behavior.
- 🔄 **Pipelines** organize a sequence of Tasks so that the output from one Task may flow into the next.
- 🌐 **Workflows** configure Tasks to operate in parallel.

### 📝 Tasks

Tasks are the core building blocks within Structures, enabling interaction with Engines, Tools, and other Griptape components.

### 🧠 Memory

- 💬 **Conversation Memory** enables LLMs to retain and retrieve information across interactions.
- 🗃️ **Task Memory** keeps large or sensitive Task outputs off the prompt that is sent to the LLM.
- 📊 **Meta Memory** enables passing in additional metadata to the LLM, enhancing the context and relevance of the interaction.

### 🚗 Drivers

Drivers facilitate interactions with external resources and services in Griptape. 
They allow you to swap out functionality and providers with minimal changes to your business logic.

#### LLM & Orchestration
- 🗣️ **Prompt Drivers**: Manage textual and image interactions with LLMs.
- 🤖 **Assistant Drivers**: Enable interactions with various “assistant” services.
- 📜 **Ruleset Drivers**: Load and apply rulesets from external sources.
- 🧠 **Conversation Memory Drivers**: Store and re

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [griptape-ai/griptape](https://github.com/griptape-ai/griptape) | github_readme |
