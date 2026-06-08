#!/usr/bin/env python3
"""
paper-grape-mcp.py — Crawl academic conference event pages (CVPR, ICCV, etc.)
and download all paper PDFs.

Core logic extracted from EasySpider's browser-automation patterns:
  - Selenium/Playwright-based page loading with configurable wait times
  - XPath / CSS-selector element extraction
  - File download via requests with proper headers

Usage:
  python paper-grape-mcp.py \\
      --url "https://cvpr.thecvf.com/virtual/2026/events/Oral" \\
      --output ./papers \\
      --headless

  # Or as a module:
  from paper_grape_mcp import PaperGrape
  grape = PaperGrape(headless=True)
  grape.harvest("https://cvpr.thecvf.com/virtual/2026/events/Oral", "./papers")
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("paper-grape")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Paper:
    title: str
    detail_url: str
    pdf_url: str = ""
    paper_id: str = ""
    authors: str = ""


@dataclass
class HarvestStats:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    papers: list[Paper] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core crawler — inspired by EasySpider's execute-stage patterns
# ---------------------------------------------------------------------------
class PaperGrape:
    """Headless browser crawler for academic paper PDFs.

    Key design decisions borrowed from EasySpider:
      - Browser-based fetching to handle JS-rendered pages
      - Configurable timeouts (page load, element wait)
      - Scroll-to-load for infinite-scroll pages
      - Retry on StaleElement / Timeout exceptions
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30_000,
        concurrency: int = 4,
        user_agent: Optional[str] = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.concurrency = concurrency
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ----- browser lifecycle ------------------------------------------------
    async def _ensure_browser(self) -> BrowserContext:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                executable_path="/usr/bin/google-chrome-stable",
            )
        if self._context is None:
            self._context = await self._browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
            )
        return self._context

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None

    # ----- page helpers -----------------------------------------------------
    async def _new_page(self) -> Page:
        ctx = await self._ensure_browser()
        page = await ctx.new_page()
        page.set_default_timeout(self.timeout)
        return page

    # ----- listing extraction -----------------------------------------------
    async def _extract_listing_links(self, url: str) -> list[Paper]:
        """Open the events listing page and extract all paper detail links.

        Handles both static HTML pages (CVPR Oral/Poster listings) and
        infinite-scroll / JS-rendered pages by scrolling to load all content.
        """
        log.info("Opening listing page: %s", url)
        page = await self._new_page()
        papers: list[Paper] = []
        seen_ids: set[str] = set()

        try:
            await page.goto(url, wait_until="domcontentloaded")
            # Give JS-rendered content time to settle
            await asyncio.sleep(2)

            # Scroll to load lazy content (EasySpider pattern)
            await self._scroll_to_bottom(page, max_scrolls=20)

            content = await page.content()
            soup = BeautifulSoup(content, "lxml")

            # Strategy A: CVPR event cards (cvpr.thecvf.com)
            cards = soup.select(".event-card")
            if cards:
                log.info("Found %d event cards", len(cards))
                for card in cards:
                    title_el = card.select_one(".event-title a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    if not href:
                        continue
                    detail_url = urljoin(url, href)
                    paper_id = card.get("data-event-id", "") or href.rstrip("/").rsplit("/", 1)[-1]
                    if paper_id in seen_ids:
                        continue
                    seen_ids.add(paper_id)

                    authors_el = card.select_one(".event-speakers")
                    authors = authors_el.get_text(strip=True) if authors_el else ""

                    papers.append(Paper(
                        title=title,
                        detail_url=detail_url,
                        paper_id=paper_id,
                        authors=authors,
                    ))

            # Strategy B: Generic — all links pointing to detail/oral/poster pages
            if not papers:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if re.search(r"/(?:oral|poster|paper|detail)/\d+", href, re.I):
                        detail_url = urljoin(url, href)
                        pid = href.rstrip("/").rsplit("/", 1)[-1]
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        papers.append(Paper(
                            title=a.get_text(strip=True),
                            detail_url=detail_url,
                            paper_id=pid,
                        ))

            # Strategy C: Generic PDF links directly on listing page
            if not papers:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith(".pdf"):
                        papers.append(Paper(
                            title=a.get_text(strip=True) or href.rsplit("/", 1)[-1],
                            detail_url="",
                            pdf_url=urljoin(url, href),
                        ))

        finally:
            await page.close()

        log.info("Extracted %d paper entries from listing", len(papers))
        return papers

    async def _scroll_to_bottom(self, page: Page, max_scrolls: int = 20):
        """Scroll down to trigger lazy loading (EasySpider scrollDown pattern)."""
        prev_height = 0
        for _ in range(max_scrolls):
            cur_height = await page.evaluate("document.body.scrollHeight")
            if cur_height == prev_height:
                break
            prev_height = cur_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.8)

    # ----- PDF URL extraction from detail page ------------------------------
    async def _extract_pdf_url(self, paper: Paper) -> Optional[str]:
        """Visit a paper's detail page and find the PDF download link."""
        if paper.pdf_url:
            return paper.pdf_url

        log.info("  Visiting detail: %s", paper.detail_url)
        page = await self._new_page()
        try:
            await page.goto(paper.detail_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)

            content = await page.content()
            soup = BeautifulSoup(content, "lxml")

            # Look for "Paper PDF" links (CVPR pattern)
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True).lower()
                href = a["href"]
                if "pdf" in text or "paper" in text:
                    if "openaccess.thecvf.com" in href or href.lower().endswith(".pdf"):
                        pdf_url = urljoin(paper.detail_url, href)
                        # CVF openaccess HTML -> PDF transformation
                        if "openaccess.thecvf.com" in pdf_url and "/html/" in pdf_url:
                            pdf_url = pdf_url.replace("/html/", "/papers/").replace(".html", ".pdf")
                        log.info("    PDF URL: %s", pdf_url)
                        return pdf_url

            # Fallback: find any .pdf link
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.lower().endswith(".pdf"):
                    return urljoin(paper.detail_url, href)

            # Fallback: try openaccess HTML -> PDF transform from any link
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "openaccess.thecvf.com" in href and "/html/" in href:
                    pdf_url = href.replace("/html/", "/papers/").replace(".html", ".pdf")
                    log.info("    Inferred PDF URL: %s", pdf_url)
                    return pdf_url

            log.warning("    No PDF link found on %s", paper.detail_url)
            return None
        finally:
            await page.close()

    # ----- PDF download -----------------------------------------------------
    async def _download_pdf(
        self,
        paper: Paper,
        output_dir: Path,
        client: httpx.AsyncClient,
    ) -> bool:
        """Download a single PDF file."""
        if not paper.pdf_url:
            return False

        # Build safe filename
        safe_title = re.sub(r"[^\w\s-]", "", paper.title)[:80].strip()
        safe_title = re.sub(r"[\s]+", "_", safe_title)
        filename = f"{paper.paper_id}_{safe_title}.pdf" if paper.paper_id else f"{safe_title}.pdf"
        filepath = output_dir / filename

        if filepath.exists():
            log.info("    Skipping (exists): %s", filename)
            return False

        headers = {
            "User-Agent": self.user_agent,
            "Referer": paper.detail_url or paper.pdf_url,
        }
        try:
            resp = await client.get(paper.pdf_url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            log.info("    Downloaded: %s  (%d bytes)", filename, len(resp.content))
            return True
        except Exception as exc:
            log.error("    Download failed [%s]: %s", paper.pdf_url, exc)
            return False

    # ----- main harvest flow ------------------------------------------------
    async def harvest(self, url: str, output_dir: str | Path) -> HarvestStats:
        """Main entry point: crawl a listing page and download all PDFs."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stats = HarvestStats()

        # Phase 1: extract listing
        papers = await self._extract_listing_links(url)
        if not papers:
            log.warning("No papers found on the listing page. Check the URL or page structure.")
            return stats
        stats.total = len(papers)

        # Phase 2: resolve PDF URLs (concurrent detail page visits)
        sem = asyncio.Semaphore(self.concurrency)

        async def _resolve(paper: Paper) -> Paper:
            async with sem:
                try:
                    pdf = await asyncio.wait_for(
                        self._extract_pdf_url(paper), timeout=25.0
                    )
                    if pdf:
                        paper.pdf_url = pdf
                except Exception as exc:
                    log.warning("  Timeout/error resolving [%s]: %s", paper.detail_url, exc)
                return paper

        log.info("Resolving PDF URLs for %d papers (concurrency=%d)...", len(papers), self.concurrency)
        results = await asyncio.gather(*(_resolve(p) for p in papers), return_exceptions=True)
        papers = [r for r in results if isinstance(r, Paper)]

        pdf_count = sum(1 for p in papers if p.pdf_url)
        log.info("Found PDF URLs for %d/%d papers", pdf_count, len(papers))

        # Phase 3: download PDFs
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def _download(paper: Paper):
                if not paper.pdf_url:
                    stats.skipped += 1
                    return
                ok = await self._download_pdf(paper, output_dir, client)
                if ok:
                    stats.downloaded += 1
                else:
                    stats.failed += 1
                stats.papers.append(paper)

            await asyncio.gather(*(_download(p) for p in papers))

        log.info(
            "Done. Total=%d  Downloaded=%d  Skipped=%d  Failed=%d",
            stats.total, stats.downloaded, stats.skipped, stats.failed,
        )
        return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def _main():
    parser = argparse.ArgumentParser(
        description="paper-grape-mcp — Crawl academic paper PDFs from conference event pages",
    )
    parser.add_argument("--url", required=True, help="Conference event listing URL")
    parser.add_argument("--output", "-o", default="./papers", help="Output directory (default: ./papers)")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run browser in headless mode (default: True)")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Show browser window")
    parser.add_argument("--concurrency", "-c", type=int, default=4,
                        help="Concurrent detail page fetches (default: 4)")
    parser.add_argument("--timeout", type=int, default=30, help="Page timeout in seconds (default: 30)")
    args = parser.parse_args()

    grape = PaperGrape(
        headless=args.headless,
        timeout=args.timeout * 1000,
        concurrency=args.concurrency,
    )
    try:
        stats = await grape.harvest(args.url, args.output)
        if stats.total == 0:
            log.warning("No papers harvested. Try a different URL or check --no-headless to debug.")
            sys.exit(1)
    finally:
        await grape.close()


if __name__ == "__main__":
    asyncio.run(_main())
