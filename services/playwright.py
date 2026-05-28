"""Playwright article fetching with trafilatura/readability extraction."""

import hashlib
import os
from pathlib import Path

from playwright.async_api import async_playwright
from readability import Document
import trafilatura
from lxml import etree, html as lxml_html

# 缓存目录，存放抓取到的原始 HTML
CACHE_DIR = Path(os.environ.get("ARTICLE_CACHE_DIR", "article_cache"))

# 验证码/反爬页面的特征字符串（小写匹配）
CAPTCHA_SIGNALS = [
    "verify you are human",
    "just a moment",
    "enable javascript and cookies",
    "checking your browser",
    "ddos protection by cloudflare",
    "please complete the security check",
    "robot or human",
    "are you a robot",
]


def _url_to_cache_path(url: str) -> Path:
    """将 URL 哈希为缓存文件路径。"""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.html"


def _is_captcha_page(html: str) -> bool:
    """检测页面是否为验证码/反爬拦截页。"""
    lower = html.lower()
    return any(signal in lower for signal in CAPTCHA_SIGNALS)


def _extract_with_trafilatura(html: str, url: str) -> dict:
    """
    使用 trafilatura 提取正文内容。
    返回: {"title": str, "content": str}
    """
    content = trafilatura.extract(
        html,
        url=url,
        output_format="html",
        include_comments=False,
        include_tables=True,
        include_images=True,
        include_formatting=True,
        no_fallback=True,
    )
    if not content or not content.strip():
        return {"title": "", "content": ""}

    metadata = trafilatura.extract_metadata(html, default_url=url)
    return {
        "title": (getattr(metadata, "title", "") or "").strip(),
        "content": _normalize_extracted_html(content),
    }


def _extract_with_readability(html: str) -> dict:
    """使用 readability-lxml 兜底提取正文内容。"""
    try:
        doc = Document(html)
        return {
            "title": doc.title(),
            "content": doc.summary(),  # 干净的正文 HTML
        }
    except Exception as e:
        # 提取失败时返回原始 HTML
        return {
            "title": "",
            "content": html,
        }


def _normalize_extracted_html(content: str) -> str:
    """Normalize extractor-specific HTML into browser-renderable markup."""
    root = lxml_html.fragment_fromstring(content, create_parent="div")
    for graphic in list(root.iter("graphic")):
        image = etree.Element("img")
        for attr in ("src", "alt", "title"):
            value = graphic.get(attr)
            if value:
                image.set(attr, value)
        graphic.getparent().replace(graphic, image)

    return "".join(
        etree.tostring(child, encoding="unicode", method="html")
        for child in root
    )


def _extract_article_content(html: str, url: str) -> dict:
    """先用 trafilatura，失败时退回 readability-lxml。"""
    try:
        extracted = _extract_with_trafilatura(html, url)
        if extracted["content"].strip():
            return extracted
    except Exception:
        pass

    return _extract_with_readability(html)


async def startup_playwright():
    """启动 Playwright 并返回 (pw, browser)。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    return pw, browser


async def shutdown_playwright(pw, browser) -> None:
    """关闭 browser 和 playwright。"""
    try:
        if browser:
            await browser.close()
    finally:
        if pw:
            await pw.stop()


async def scrape_article(browser, url: str, timeout: int = 60000, bypass_cache: bool = False) -> dict:
    """
    抓取文章页面 HTML，带缓存、验证码检测和正文提取。

    返回:
        {
            "html": str,          # 提取后的正文 HTML（验证码时为空字符串）
            "title": str,         # 文章标题
            "from_cache": bool,   # 是否来自缓存
            "captcha": bool,      # 是否触发验证码
        }
    """
    cache_path = _url_to_cache_path(url)

    # 命中缓存直接返回（仅在未 bypass_cache 时）
    if not bypass_cache and cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
        extracted = _extract_article_content(html, url)
        return {
            "html": extracted["content"],
            "title": extracted["title"],
            "from_cache": True,
            "captcha": False,
        }

    context = await browser.new_context()
    page = await context.new_page()
    try:
        await page.goto(url, timeout=timeout)
        await page.wait_for_load_state("networkidle")
        html = await page.content()
    finally:
        try:
            await page.close()
        except Exception:
            pass
        try:
            await context.close()
        except Exception:
            pass

    # 验证码检测
    if _is_captcha_page(html):
        return {
            "html": "",
            "title": "",
            "from_cache": False,
            "captcha": True,
        }

    # 写入缓存（原始 HTML）
    cache_path.write_text(html, encoding="utf-8")

    # 提取正文
    extracted = _extract_article_content(html, url)
    return {
        "html": extracted["content"],
        "title": extracted["title"],
        "from_cache": False,
        "captcha": False,
    }
