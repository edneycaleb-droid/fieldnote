# Converting Documents to Markdown for AI Pipelines

## Introduction
MarkItDown is a lightweight Python utility designed to convert various file formats into Markdown. This is particularly useful for preparing documents to be used with Large Language Models (LLMs) and text analysis pipelines, as it preserves important document structure and content.

## Installing MarkItDown
To install MarkItDown, use pip: `pip install 'markitdown[all]'`.

## Configuring the Environment
Before converting files, ensure your environment is set up correctly. This may involve creating a virtual environment and installing necessary dependencies.

## Converting Files to Markdown
MarkItDown can convert a wide range of file formats, including PDF, PowerPoint, Word, Excel, images, audio, HTML, and more. The conversion process can be performed using the command line or through the Python API.

### Command-Line Conversion
To convert a file using the command line, use the following command: `markitdown path-to-file.pdf > document.md`.

### Python API Conversion
For more advanced use cases or integration into larger projects, MarkItDown provides a Python API. Here’s an example of how to use it:
```python
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert("test.xlsx")
print(result.text_content)
```

## Related Skills
- [MarkItDown](../markitdown/markitdown.md)
- [Webrover](../webrover/webrover.md)
- [Rag Techniques](../rag_techniques/rag_techniques.md)

## Sources

| Date | Video | Transcript |
|------|-------|------------|
| 2026-07-24 | [microsoft/markitdown](https://github.com/microsoft/markitdown) | github_readme |
