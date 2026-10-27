#!/usr/bin/env python3
"""build_pdf - prints the Operating Procedures site (the tuple pages) to one PDF binder.

The same HTML the website uses, opened with ?print=1 (every page in order,
a cover and contents, no review buttons), printed by Chromium through
Playwright. Letter size, page numbers in the footer.

    python synth/procedures/build_pdf.py [site.html] [out.pdf]
    LA_PDF_AGENT=03 python synth/procedures/build_pdf.py ...   # one agent's pages only
"""
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

FOOTER = ('<div style="font-size:8px;width:100%;padding:0 12mm;color:#555;display:flex;'
          'justify-content:space-between;font-family:Arial,sans-serif">'
          '<span>ListingAssistants · Operating Procedures</span>'
          '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')


def build_pdf(html_path: str, pdf_path: str, agent: str = "") -> str:
    from playwright.sync_api import sync_playwright
    url = pathlib.Path(os.path.abspath(html_path)).as_uri() + "?print=1" + (f"&agent={agent}" if agent else "")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_selector(".cover")
        if errors:
            browser.close()
            raise SystemExit("page errors while printing: " + "; ".join(errors))
        page.emulate_media(media="print")
        page.pdf(path=pdf_path, format="Letter", print_background=True, outline=True, tagged=True,
                 margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
                 display_header_footer=True, header_template="<div></div>", footer_template=FOOTER)
        browser.close()
    return pdf_path


if __name__ == "__main__":
    a = sys.argv[1:]
    src = a[0] if a else os.path.join(HERE, "site", "procedures.html")
    out = a[1] if len(a) > 1 else os.path.join(HERE, "site", "procedures.pdf")
    agent = os.environ.get("LA_PDF_AGENT", "")
    print(build_pdf(src, out, agent))
