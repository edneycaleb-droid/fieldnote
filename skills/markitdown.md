# markitdown

## Description

Python tool for converting files and office documents to Markdown.

## Steps

- PowerPoint
- Images (EXIF metadata and OCR)
- Audio (EXIF metadata and speech transcription)
- Text-based formats (CSV, JSON, XML)
- ZIP files (iterates over contents)
- YouTube URLs
- ... and more!
- `[all]` Installs all optional dependencies

## Tools

autogen, openai, docker, autogen-extension, langchain, markdown, microsoft-office, pdf, Python

## Source

GitHub: [microsoft/markitdown](https://github.com/microsoft/markitdown) ⭐ 168,583

## README Excerpt

# MarkItDown

[](https://pypi.org/project/markitdown/)

[](https://github.com/microsoft/autogen)

> [!IMPORTANT]
> MarkItDown performs I/O with the privileges of the current process. Like open() or requests.get(), it will access resources that the process itself can access. Sanitize your inputs in untrusted environments, and call the narrowest `convert_*` function needed for your use case (e.g., `convert_stream()`, or `convert_local()`). See the Security Considerations section of the documentation for more information.

MarkItDown is a lightweight Python utility for converting various files to Markdown for use with LLMs and related text analysis pipelines. To this end, it is most comparable to textract, but with a focus on preserving important document structure and content as Markdown (including: headings, lists, tables, links, etc.) While the output is often reasonably presentable and human-friendly, it is meant to be consumed by text analysis tools -- and may not be the best option for high-fidelity document conversions for human consumption.

MarkItDown currently supports the conversion from:

- PDF
- PowerPoint
- Word
- Excel
- Images (EXIF metadata and OCR)
- Audio (EXIF metadata and speech transcription)
- HTML
- Text-based formats (CSV, JSON, XML)
- ZIP files (iterates over contents)
- YouTube URLs
- EPubs
- ... and more!

## Why Markdown?

Markdown is extremely close to plain text, with minimal markup or formatting, but still
provides a way to represent important document structure. Mainstream LLMs, such as
OpenAI's GPT-4o, natively "_speak_" Markdown, and often incorporate Markdown into their
responses unprompted. This suggests that they have been trained on vast amounts of
Markdown-formatted text, and understand it well. As a side benefit, Markdown conventions
are also highly token-efficient.

## Prerequisites
MarkItDown requires Python 3.10 or higher. It is recommended to use a virtual environment to avoid dependency conflicts.

With the standard Python

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [microsoft/markitdown](https://github.com/microsoft/markitdown) | github_readme |
