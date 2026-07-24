# DeepSeek-671B-SFT-Guide

## Description

An open-source solution for full parameter fine-tuning of DeepSeek-V3/R1 671B, including complete code and scripts from training to inference, as well as some practical experiences and conclusions. (D

## Steps

- Implemented modeling files containing DeepSeek-V3/R1 training logic (see `./model`, code logic completed based on Deepse
- Implemented full parameter fine-tuning of DeepSeek-V3/R1 671B based on data parallelism (DeepSpeed ZeRO) + sequence para
- Summarized the entire process of model training and deployment, including pitfalls, encountered problems, and solutions.
- `./code/scripts/sft_deepseek.py`: Configuration file for sft training, including hyperparameter settings, model and toke
- `./code/scripts/sft_deepseek.sh`: sft training startup script, which is an execution file for a single node, so it needs
- Overwrite the `modeling_deepseek.py` file provided in the `./model` directory of this project to the corresponding origi
- Use pdsh to start training, execute the command `pdsh -R ssh -w node[0-31] 'bash ./code/scripts/sft_deepseek.sh'` on the
- Set environment variables (node0~node3).

## Tools

vllm, huggingface, openai, ray, transformers, deepseek-r1, llm, moe, python, sft

## Source

GitHub: [ScienceOne-AI/DeepSeek-671B-SFT-Guide](https://github.com/ScienceOne-AI/DeepSeek-671B-SFT-Guide) ⭐ 811

## README Excerpt

# DeepSeek-V3/R1-671B Full Parameter Fine-Tuning Guide

[](https://github.com/ScienceOne-AI/DeepSeek-671B-SFT-Guide)
[](https://opensource.org/licenses/Apache-2.0)

中文版 ｜ English

An open-source solution for full parameter fine-tuning of DeepSeek-V3/R1 671B, including complete code and scripts from training to inference, as well as some practical experiences and conclusions, jointly launched by the Institute of Automation of the Chinese Academy of Sciences and Beijing Wenge Technology Co. Ltd.

## 🌟 Project Highlights
- Implemented modeling files containing DeepSeek-V3/R1 training logic (see `./model`, code logic completed based on Deepseek-V3 paper and Deepseek-V2 modeling files);
- Implemented full parameter fine-tuning of DeepSeek-V3/R1 671B based on data parallelism (DeepSpeed ZeRO) + sequence parallelism (SP);
- Summarized the entire process of model training and deployment, including pitfalls, encountered problems, and solutions.

## 🚀 Quick Start
### 1. Hardware Configuration

The configuration of a single server is shown in the table below. There are 32 machines with the same configuration in the cluster, sharing 100TB of storage space, mounted at `/nfs`. The operating system of the machines is Ubuntu 22.04, with IB network communication between machines, NVLink communication between GPUs, and CUDA version 12.6.

| Component  | Specification/Version

| Command to View Details  |

|------------|-----------------------------|--------------------------| 
| GPU

| 8 x NVIDIA H100 80GB HBM3

| `nvidia-smi`

|

| CPU

| Intel(R) Xeon(R) Platinum 8463B (96 Cores) | `lscpu` |

| Memory

| 2.0TB DDR4

| `free -h`

| 
| Storage

| 100TB NVMe SSD

| `df -h`

| 
| Network

| InfiniBand 400G

| `ibstat`

| 
| OS

| Ubuntu 22.04

| `uname -a`

| 
| CUDA

| CUDA 12.6

| `nvcc -V`

|

### 2. Environment Setup

We extended and improved the xtuner framework to support full parameter fine-tuning of Deepseek V3/R1 (i.e., `DeepseekV3ForCausalLM` model architecture), supporting d

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [ScienceOne-AI/DeepSeek-671B-SFT-Guide](https://github.com/ScienceOne-AI/DeepSeek-671B-SFT-Guide) | github_readme |
