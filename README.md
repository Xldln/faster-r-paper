# faster-r-paper

CVPR/ICCV 等顶会论文的自动化获取 → 文本提取 → AI 总结管线。

## 工具

### paper-grape-mcp.py

从会议官网自动抓取论文 PDF，支持 Selenium/Playwright 方式加载页面并批量下载。

```bash
python paper-grape-mcp.py --url <event-url> --output ./papers
```

### txt-paper-mcp.py

基于 MCP 协议的 PDF 文本提取服务，将论文 PDF 解析为纯文本（含分页标记），供下游摘要使用。

```bash
# 单篇提取
python txt-paper-mcp.py --pdf paper.pdf -o ./txt

# 批量提取
python txt-paper-mcp.py --pdf-dir ./papers -o ./txt
```

## Skill

### paper-summarizer

Crush skill（`paper-summarizer/SKILL.md`），利用提取出的 `.txt` 文件自动生成结构化中文论文摘要（.md），涵盖标题、单位、问题、摘要、创新点、总结六个维度。
