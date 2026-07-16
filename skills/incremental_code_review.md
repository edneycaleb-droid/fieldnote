# Efficient Code Review with AI: Building a Persistent Graph Map and Reducing Tokens

## Description
Efficient code review with AI requires intelligent tools to minimize token waste and boost productivity. By building a local-first code intelligence graph using Tree-sitter and storing it as a persistent graph map with the code-review-graph library, you can reduce token waste by up to 528x.

## Steps
1. Parse the codebase into an Abstract Syntax Tree (AST) using Tree-sitter
2. Build a structural map of the code with Tree-sitter, tracking changes incrementally
3. Use the graph to compute the minimal set of files the AI assistant needs to read for a given review task
4. Implement incremental updates in under 2 seconds using SHA-256 hash checks and re-parsing only changed files
5. Install code-review-graph using pip or pipx and run 'code-review-graph build' to set up the graph map
6. Use 'code-review-graph install' to configure and install supported AI coding tools like Codex, Claude Code, and Gemini CLI with the graph-aware instructions in your platform rules
7. Parse your codebase with Tree-sitter and store it as a graph of nodes and edges to enable efficient query-based reviews

## Tools
* code-review-graph: the library used to build and query the persistent graph map
* Tree-sitter: the parser used to parse the codebase and create the graph
* Codex: an AI coding tool supported by the code-review-graph library
* Claude Code

## Concepts
* Persistent Graph Map
* Token Waste Reduction
* AI Coding Tools
* Efficient Code Review
* Code Intelligence
* Local-First
* Incremental Updates
* Graph-Based Analysis

## Related Skills
* Build Production-Ready LLM Applications with Haystack
* Building Effective AI Agents for Automation and Productivity
* Orchestration
* AI Coding

## Arena
* title_winner: merged
* desc_winner: Efficient code review with AI requires intelligent tools to minimize token waste and boost productivity.
* steps_a: 4
* steps_b: 3
* steps_merged: 7
* github_tools_added: 3

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-16 | [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) | github_readme |
