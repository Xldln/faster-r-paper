---
name: paper-summarizer
description: "Use when the user wants to summarize academic papers (especially CV/ML papers from conferences like CVPR, ICCV, NeurIPS, etc.) from extracted plain-text (.txt) files into a structured, well-formatted Markdown (.md) summary written entirely in Chinese. The summary includes the paper title, problem addressed, abstract, first-author affiliation, innovations, work summary, and GitHub repository link if available. Trigger keywords: \"summarize paper\", \"论文总结\", \"paper summary\", \"总结这篇文章\", or any request to create a structured summary from academic paper text. Also trigger when the user wants to batch-extract PDFs and summarize them."
user-invocable: true
license: MIT
---

# Paper Summarizer

Summarize academic papers from extracted plain-text (.txt) files into a structured Markdown summary.

**硬性规则：最终的 .md 文件必须全部使用中文撰写。** 仅论文标题、作者名、机构名、GitHub URL 可保留原文。

## Prerequisites

For PDF-to-text extraction, use `txt-paper-mcp.py` located in the project root:
```bash
# Single PDF
python txt-paper-mcp.py --pdf <path-to-pdf> -o <output-dir>

# Batch extract all PDFs in a directory
python txt-paper-mcp.py --pdf-dir <dir-containing-pdfs> -o <output-dir>
```

If `.txt` files have already been extracted, skip this step.

## Workflow

1. **Locate the source**: find the `.txt` file(s) for the paper(s). If only a PDF exists and no `.txt` yet, run `txt-paper-mcp.py` first.

2. **Read the text**: load the full `.txt` file. The text has page markers like `--- Page N ---`. Do not include these markers in the output.

3. **Extract key information from the paper text**:
   - **文章题目 (Title)**: typically on page 1, the largest heading before the abstract
   - **第一作者单位 (First Author Affiliation)**: listed near the author names, usually on page 1
   - **文章解决的问题 (Problem)**: what gap or challenge does the paper address? Look in the Introduction
   - **文章摘要 (Abstract)**: a concise restatement of the abstract plus key contributions; do NOT copy-paste verbatim — rephrase
   - **文章创新点 (Innovations)**: list 2-4 concrete, specific contributions as bullet points
   - **工作总结 (Work Summary)**: brief assessment of what the work achieves and its significance
   - **GitHub 链接 (GitHub Link)**: search the text for `github.com` URLs; include ALL found. If none, state "未提供 (Not provided)"

4. **Write the `.md` file**: save to the same directory as the source `.txt`, named `<paper-short-name>_summary.md`.

## Output Format

Use this exact template — the structure, table layout, and section headings must match:

```markdown
# <Paper Title>

| **条目** | **内容** |
|----------|----------|
| **文章题目** | <full paper title> |
| **第一作者单位** | <institution name> (in both English and Chinese if known) |
| **GitHub 代码仓库** | [<repo-url>](<repo-url>)  or 未提供 |

## 文章解决的问题

<2-4 sentences describing the core problem. Be specific — mention the method/domain and the concrete challenge.>

## 文章摘要

<4-6 sentences rephrasing the abstract and key contributions. Do NOT copy-paste. Use your own words in Chinese.>

## 文章创新点

<Numbered list, each item 2-4 sentences with concrete detail. Avoid vague claims like "proposed a novel method" — say what the method does and why it works.>

1. **<Innovation 1 title>**：<explanation>
2. **<Innovation 2 title>**：<explanation>
3. **<Innovation 3 title>**：<explanation>

## 工作总结

<3-5 sentences assessing what the paper achieved, its significance, limitations (if mentioned), and potential impact. End with a forward-looking statement.>
```

## Formatting Rules

- **ALL section content must be in Chinese** (except the paper title, author names, institution names, and GitHub URLs which stay in their original language).
- Use `karpathy-guidelines` style: clean, minimalist, data-dense, no fluff.
- The summary table must use `| **条目** | **内容** |` format exactly.
- GitHub URLs: use markdown link syntax `[url](url)`.
- Page markers (`--- Page N ---`) from the source txt must NOT appear in the output.
- If any field cannot be found, write "未提供 (Not provided)" rather than omitting it.
- Maximum summary length: the entire .md should be readable in under 3 minutes.
