"""Screenshot every Grafana dashboard for the README (``make screenshots``).

Runs in the official Playwright image against the local stack: each dashboard opens in kiosk mode at 1600 px wide,
the viewport grows to the whole grid so every panel renders, and the PNG lands in ``docs/img/``.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

GRAFANA = "http://localhost:3000"
WIDTH = 1600
# uid -> file name in docs/img
DASHBOARDS = {
    "mallorca-overview": "inicio",
    "mallorca-tourism-resources": "turismo-y-recursos",
    "mallorca-climate-water": "clima-y-agua",
    "mallorca-mobility": "movilidad",
    "mallorca-weather": "tiempo-y-entorno",
    "mallorca-operations": "operacion",
}
_GRID_BOTTOM = (
    "Math.max(...[...document.querySelectorAll('.react-grid-layout')].map(e => e.getBoundingClientRect().bottom), 1000)"
)


def main(out_dir: Path) -> None:
    """Write one PNG per dashboard into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        # An explicit locale: Grafana fails to boot with the container default (en-US@posix).
        page = browser.new_page(color_scheme="dark", locale="es-ES", timezone_id="Europe/Madrid")
        for uid, name in DASHBOARDS.items():
            page.set_viewport_size({"width": WIDTH, "height": 1000})
            page.goto(f"{GRAFANA}/d/{uid}?orgId=1&kiosk", wait_until="networkidle")
            page.wait_for_timeout(3000)
            # Kiosk mode scrolls inside the page and panels below the fold never load: show the whole grid.
            page.set_viewport_size({"width": WIDTH, "height": int(page.evaluate(_GRID_BOTTOM)) + 40})
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(6000)
            page.screenshot(path=out_dir / f"{name}.png")
            print(f"{name}.png")  # noqa: T201 - progress of a command-line tool
        browser.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/img"))
