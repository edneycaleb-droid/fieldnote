# Implementing PaSa: An LLM Agent for Comprehensive Academic Paper Search

## Introduction
PaSa is an advanced paper search agent powered by large language models. It can autonomously make a series of decisions, including invoking search tools, reading papers, and selecting relevant references, to ultimately obtain comprehensive and accurate results for complex scholarly queries.

## Quick Start
You can prepare a detailed description of your academic search needs, and search for papers on https://pasa-agent.ai

## Architecture
The PaSa system consists of two LLM agents, Crawler and Selector. The Crawler processes the user query and can access papers from the paper queue. It can autonomously invoke the search tool, expand citations, or stop processing of the current paper. All papers collected by the Crawler are appended to the paper queue. The Selector reads each paper in the paper queue to determine whether it meets the criteria specified in the user query.

## Dataset
All the datasets are available at pasa-dataset

### AutoScholarQuery
AutoScholarQuery is a synthetic but high-quality dataset of academic queries and related papers, specifically curated for the AI field.

### RealScholarQuery
RealScholarQuery is a test dataset consisting of 50 real-world and fine-grained research queries raised by AI researchers to use the system. The answers to each query are identified as comprehensively as possible by the professional annotators through various retrieval methods.

## Experiments
### Baselines
We evaluate our paper search agent on both the test set of AutoScholarQuery and RealScholarQuery. We compare PaSa-7b against the following baselines:
- **Google.** Use Google to search the query directly.
- **Google Scholar.** Queries are submitted directly to Google Scholar.
- **Google with GPT-4o.** We first employ GPT-4o to paraphrase the scholar query. The paraphrased query is then searched on Google.
- **ChatGPT.** We submit the scholar query to ChatGPT, powered by search-enabled GPT-4o. Due to the need for manual query submission, we evaluate only 100 randomly sampled instances from the AutoScholarQuery test set.
- **GPT-o1.** Prompt GPT-o1 to process the scholar query.
- **PaSa-GPT-4o.** Prompt GPT-4o within the PaSa framework. It can perform multiple searches, paper reading, and citation network crawling.

## Run Locally
### Data Preparation
Download dataset from pasa-dataset and save it in the data folder.

### Model Preparation
Download model checkpoints pasa-7b-crawler and pasa-7b-selector and save it in the checkpoints folder.

### Run Pasa
`python run_paper_agent.py`

## Training Your Own Agent
We modify the code of `trl` and `transformers`, you can do SFT and PPO training after cloning and installing them.

### Install dependencies
`git clone git@github.com:hyc2026/trl.git` and `git clone git@github.com/hyc2026/transformers.git` and `pip install -r requirements.txt`

### Selector SFT Training
`accelerate launch ...` and `examples/scripts/sft.py ...`

### Crawler SFT Training
`accelerate launch ...` and `examples/scripts/sft.py ...`

### Crawler PPO Training
`accelerate launch ...` and `examples/scripts/ppo/ppo_tldr.py ...`

## Citation
Please cite us as:
```BibTeX
@misc{he2024pasa,
  title={PaSa: An LLM Agent for Comprehensive Academic Paper Search},
  author={Yichen He and Guanhua Huang and Peiyuan Feng and Yuan Lin and Yuchen Zhang and Hang Li and Weinan E},
  year={2025},
  eprint={2501.10120},
  archivePrefix={arXiv},
  primaryClass={cs.IR}
}
```

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-21 | [bytedance/pasa](https://github.com/bytedance/pasa) | github_readme |
