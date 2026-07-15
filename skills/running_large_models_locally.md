# Efficiently Running Large AI Models on Local Machines

## Introduction
Running large AI models on local machines can be challenging due to limited RAM. However, with the right techniques and tools, it is possible to efficiently process complex models without relying on data centers or cloud services.

## Steps to Run Large Models Locally
1. **Understand the concept of mixture of experts models**: Mixture of experts models are designed to reduce memory usage by only activating a subset of experts for each input.
2. **Implement model pruning and expert caching**: Prune the model to remove unnecessary parameters and cache frequently used experts to minimize disk reads.
3. **Utilize tools like Colibri**: Colibri is a tool that streams model experts off an SSD, reducing the need for large amounts of RAM.
4. **Optimize SSD usage**: Optimize SSD usage for reading model experts, minimizing wear and tear.
5. **Explore predictive routing**: Predictive routing involves guessing which experts will be needed next, reducing disk reads and improving performance.

## Tools
* Colibri: A tool for streaming model experts off an SSD
* AntiRaz: A metal and C engine for streaming DeepSeek's experts
* DS4: A engine for streaming model experts
* Lama CPP: A framework for running large models on local machines
* VLLM: A framework for running large models on local machines

## Concepts
* Mixture of experts models: A type of model that reduces memory usage by only activating a subset of experts for each input
* Model pruning: The process of removing unnecessary parameters from a model
* Expert caching: The process of caching frequently used experts to minimize disk reads
* SSD optimization: The process of optimizing SSD usage for reading model experts
* Predictive routing: The process of guessing which experts will be needed next to reduce disk reads

## Related Skills
* building_ai_agents: A skill that teaches how to build effective AI agents for automation

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-15 | [We Just Hit the Local LLM Tipping Point (Colibri)](https://youtu.be/19xCOJxWU0A?is=daU4YDM0FL-5gpsh) | whisper |
