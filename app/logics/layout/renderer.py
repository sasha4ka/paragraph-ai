from pathlib import Path

from playwright.async_api import async_playwright
from selectolax.lexbor import LexborHTMLParser

from app.logics.layout.validator import validate

SINGLE_COLUMN_SIZE = (800, 1000)
TWO_COLUMN_SIZE = (1600, 1000)

_CARD_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
    }
    body {
      color: #17212b;
      font-family: Arial, Helvetica, sans-serif;
      background: #2A7B9B;
      background: linear-gradient(30deg, rgba(42, 123, 155, 1) 0%, rgba(87, 199, 133, 1) 50%, rgba(169, 138, 194, 1) 100%);
    }
    .card {
      display: flex;
      flex-direction: column;
      width: 100vw;
      height: 100vh;
      padding: 44px 52px;
      overflow: hidden;
    }
    card-title {
      display: block;
      flex: 0 0 auto;
      margin: 0 0 30px;
      color: #102a38;
      font-size: 38px;
      font-weight: 700;
      line-height: 1.15;
      text-align: center;
      overflow-wrap: anywhere;
      text-shadow: 0 1px 0 rgba(255, 255, 255, .55);
    }
    .card-content {
      flex: 1 1 auto;
      min-height: 0;
      overflow: hidden;
      padding: 28px 32px;
      border: 1px solid rgba(255, 255, 255, .55);
      border-radius: 24px;
      background: rgba(255, 255, 255, .58);
      box-shadow: 0 12px 36px rgba(17, 43, 70, .16),
                  inset 0 1px 0 rgba(255, 255, 255, .72);
      -webkit-backdrop-filter: blur(24px) saturate(140%);
      backdrop-filter: blur(24px) saturate(140%);
      font-size: 20px;
      line-height: 1.45;
    }
    .card-content > * { margin-top: 0; margin-bottom: 18px; }
    .card-content h1, .card-content h2,
    .card-content h3, .card-content h4 {
      color: #143b4e;
      line-height: 1.2;
      break-after: avoid;
    }
    .card-content h1 { font-size: 30px; }
    .card-content h2 { font-size: 26px; }
    .card-content h3 { font-size: 23px; }
    .card-content h4 { font-size: 21px; }
    .card-content p { margin-top: 0; }
    .card-content ul, .card-content ol, .card-content dl {
      padding-left: 1.4em;
    }
    .card-content li { margin-bottom: 7px; }
    .card-content table {
      width: 100%;
      border-collapse: collapse;
      break-inside: avoid;
      font-size: 17px;
    }
    .card-content th, .card-content td {
      padding: 8px 10px;
      border: 1px solid rgba(23, 33, 43, .35);
      text-align: left;
      vertical-align: top;
    }
    .card-content th { background: rgba(255, 255, 255, .45); }
    .card-content code {
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(255, 255, 255, .45);
      font-family: "Courier New", monospace;
    }
    .card-content formula, .card-content inline-formula {
      display: inline-block;
      padding: 2px 8px;
      border: 1px dashed rgba(16, 42, 56, .65);
      border-radius: 6px;
      background: rgba(255, 255, 255, .45);
      font-size: 0;
      vertical-align: baseline;
    }
    .card-content formula { display: block; width: fit-content; margin: 8px 0; }
    .card-content formula::before {
      content: "[Формула]";
      color: #102a38;
      font-size: 16px;
    }
    .card-content inline-formula::before {
      content: "[формула]";
      color: #102a38;
      font-size: 15px;
    }
    .two-columns .card-content {
      column-count: 2;
      column-gap: 48px;
      column-fill: auto;
    }
    .two-columns .card-content > * { break-inside: avoid-column; }
  </style>
</head>
<body>
  <main class="card">
    <card-title>__CARD_TITLE__</card-title>
    <div class="card-content">__CARD_CONTENT__</div>
  </main>
</body>
</html>"""


def _build_document(html_text: str) -> str:
    if not validate(html_text):
        raise ValueError(
            "Invalid card HTML: expected <card-title> followed by <card-body>"
        )

    tree = LexborHTMLParser(html_text)
    title = tree.css_first("card-title")
    card_body = tree.css_first("card-body")
    if title is None or card_body is None:
        raise ValueError("Invalid card HTML: title or body is missing")

    before_title, after_title = _CARD_TEMPLATE.split("__CARD_TITLE__", 1)
    before_content, after_content = after_title.split("__CARD_CONTENT__", 1)
    return (
        before_title
        + (title.inner_html or "")
        + before_content
        + (card_body.inner_html or "")
        + after_content
    )


async def render_html(html_text: str, output: Path) -> None:
    """Render a validated card to a fixed 800x1000 or 1600x1000 image."""
    document = _build_document(html_text)
    output.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={
                    "width": SINGLE_COLUMN_SIZE[0],
                    "height": SINGLE_COLUMN_SIZE[1],
                },
                device_scale_factor=1,
            )
            await page.set_content(document, wait_until="load")
            use_two_columns = await page.evaluate(
                """() => {
              const content = document.querySelector('.card-content');
              return content.scrollHeight > content.clientHeight;
            }"""
            )

            if use_two_columns:
                await page.evaluate(
                    "document.documentElement.classList.add('two-columns')"
                )
                await page.set_viewport_size(
                    {
                        "width": TWO_COLUMN_SIZE[0],
                        "height": TWO_COLUMN_SIZE[1],
                    }
                )
                content_fits = await page.evaluate(
                    """() => {
                    const content = document.querySelector('.card-content');
                    return content.scrollWidth <= content.clientWidth;
                  }"""
                )
                if not content_fits:
                    raise ValueError(
                        "Card content exceeds the available two-column layout; "
                        "split it across multiple cards."
                    )

            if output.suffix.lower() in {".jpg", ".jpeg"}:
                await page.screenshot(
                    path=str(output), type="jpeg", quality=100, full_page=False
                )
            else:
                await page.screenshot(path=str(output), type="png", full_page=False)
        finally:
            await browser.close()
