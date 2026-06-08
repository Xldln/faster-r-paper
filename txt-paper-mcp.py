#!/usr/bin/env python3
"""
translate-paper-mcp.py — Extract text from academic PDFs.

Usage (MCP server):
  python translate-paper-mcp.py

Usage (CLI):
  python translate-paper-mcp.py --pdf <path> [--output dir]
  python translate-paper-mcp.py --pdf-dir <dir> [--output dir]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pdfplumber
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("translate-paper")

mcp = FastMCP("translate-paper-mcp")


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------
def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF file, preserving page breaks."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages_text = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages_text.append(f"--- Page {i + 1} ---\n{text.strip()}")

    return "\n\n".join(pages_text)


# ---------------------------------------------------------------------------
# Save output
# ---------------------------------------------------------------------------
def save_output(text: str, output_dir: str, pdf_name: str) -> Path:
    """Save extracted text to a file."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf_name).stem
    fname = f"{stem}_extracted.txt"
    out_path = out_dir / fname
    out_path.write_text(text, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# MCP Tool: extract a single PDF
# ---------------------------------------------------------------------------
@mcp.tool(
    name="extract_paper",
    annotations={
        "title": "Extract Text from Academic Paper PDF",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def extract_paper(
    pdf_path: str,
    output_dir: str = "./extracted",
) -> str:
    """
    Extract text from a PDF and save to a text file.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save extracted text (default: ./extracted).

    Returns:
        JSON string with the path to the extracted text file and character count.
    """
    try:
        log.info("Extracting text from %s ...", pdf_path)
        raw_text = extract_text(pdf_path)

        if not raw_text.strip():
            return json.dumps({"error": "No text could be extracted from the PDF. It may be scanned or image-based."},
                              indent=2)

        ext_path = save_output(raw_text, output_dir, pdf_path)
        log.info("Extracted text saved: %s  (%d chars)", ext_path, len(raw_text))

        return json.dumps({
            "extracted_file": str(ext_path),
            "chars": len(raw_text),
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        log.error("Failed: %s", e)
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2)


# ---------------------------------------------------------------------------
# MCP Tool: batch extract all PDFs in a directory
# ---------------------------------------------------------------------------
@mcp.tool(
    name="extract_papers_batch",
    annotations={
        "title": "Batch Extract All PDFs in a Directory",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def extract_papers_batch(
    pdf_dir: str,
    output_dir: str = "./extracted",
) -> str:
    """
    Extract text from all PDFs in a directory.

    Args:
        pdf_dir: Directory containing PDF files.
        output_dir: Directory to save extracted text (default: ./extracted).

    Returns:
        JSON summary of all processed files.
    """
    pdf_dir_path = Path(pdf_dir)
    if not pdf_dir_path.exists():
        return json.dumps({"error": f"Directory not found: {pdf_dir}"})

    pdf_files = sorted(pdf_dir_path.glob("*.pdf"))
    if not pdf_files:
        return json.dumps({"error": f"No PDF files found in {pdf_dir}"})

    results = []
    for pdf_file in pdf_files:
        log.info("[%d/%d] Processing %s ...", len(results) + 1, len(pdf_files), pdf_file.name)
        try:
            raw_text = extract_text(str(pdf_file))
            if not raw_text.strip():
                results.append({"file": pdf_file.name, "status": "skipped", "reason": "no extractable text"})
                continue

            ext_path = save_output(raw_text, output_dir, pdf_file.name)
            results.append({
                "file": pdf_file.name,
                "status": "ok",
                "extracted": str(ext_path),
                "chars": len(raw_text),
            })
        except Exception as e:
            results.append({"file": pdf_file.name, "status": "error", "error": str(e)})

    summary = {
        "total": len(pdf_files),
        "succeeded": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
    return json.dumps(summary, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main():
    parser = argparse.ArgumentParser(description="Extract text from academic paper PDFs")
    parser.add_argument("--pdf", help="Path to PDF file (single file mode)")
    parser.add_argument("--pdf-dir", help="Directory of PDF files (batch mode)")
    parser.add_argument("--output", "-o", default="./extracted", help="Output directory")
    args = parser.parse_args()

    if args.pdf:
        raw = extract_text(args.pdf)
        ext_path = save_output(raw, args.output, args.pdf)
        print(f"Extracted: {ext_path}  ({len(raw)} chars)")
    elif args.pdf_dir:
        pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
        if not pdfs:
            print(f"No PDFs found in {args.pdf_dir}")
            sys.exit(1)
        for i, pdf in enumerate(pdfs, 1):
            print(f"[{i}/{len(pdfs)}] {pdf.name} ...")
            raw = extract_text(str(pdf))
            ext_path = save_output(raw, args.output, pdf.name)
            print(f"  → {ext_path.name}")
        print(f"Done. {len(pdfs)} papers extracted.")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _main()
    else:
        mcp.run()
