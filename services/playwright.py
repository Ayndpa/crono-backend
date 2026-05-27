# services/playwright.py
import hashlib
import os
from pathlib import Path
from playwright.async_api import async_playwright
from typing import Tuple
from readability import Document

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


def _extract_readable_content(html: str) -> dict:
    """
    使用 readability 提取正文内容。
    返回: {"title": str, "content": str}
    """
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


async def startup_playwright() -> Tuple[object, object]:
    """
    启动 Playwright 并返回 (pw, browser)。
    在 FastAPI 的 lifespan 中调用。
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    return pw, browser


async def shutdown_playwright(pw, browser) -> None:
    """
    关闭 browser 和 playwright。
    """
    try:
        if browser:
            await browser.close()
    finally:
        if pw:
            await pw.stop()


async def scrape_article(browser, url: str, timeout: int = 60000, bypass_cache: bool = False) -> dict:
    """
    抓取文章页面 HTML，带缓存、验证码检测和 readability 提取。

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
        extracted = _extract_readable_content(html)
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
        html = await page.content()  # 获取完整 HTML（含动态渲染结果）

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
        extracted = _extract_readable_content(html)
        return {
            "html": extracted["content"],
            "title": extracted["title"],
            "from_cache": False,
            "captcha": False,
        }
    finally:
        try:
            await page.close()
        except Exception:
            pass
        try:
            await context.close()
        except Exception:
            pass
