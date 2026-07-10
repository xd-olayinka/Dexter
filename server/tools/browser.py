from tools.registry import Tool, registry


async def browse_url(url: str, selector: str = "body") -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Browser automation unavailable — install playwright"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            element = page.locator(selector).first
            text = await element.inner_text(timeout=5000)
            await browser.close()
            if len(text) > 8000:
                text = text[:8000] + "\n\n... (truncated)"
            return text
    except Exception as e:
        return f"Browse failed: {type(e).__name__}: {e}"


registry.register(
    Tool(
        name="browse_url",
        description="Open a URL and extract its text content",
        parameters={
            "url": {"type": "string", "description": "URL to visit"},
            "selector": {
                "type": "string",
                "description": "Optional CSS selector to extract specific content",
                "default": "body",
            },
        },
        handler=browse_url,
    )
)
