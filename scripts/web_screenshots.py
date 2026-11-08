"""Screenshot every dashboard of the web front end for the README (``make screenshots``).

Runs in the official Playwright image against the local stack (service ``web``, port 3002): each dashboard opens at
1440 px wide in the light theme, waits for its data, charts and map tiles, and lands as a PNG of the whole page in
``docs/img/web/``. The home page is also taken in the dark theme, to show both.
"""

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

WEB = "http://localhost:3002"
WIDTH = 1440
# route -> file name in docs/img/web
DASHBOARDS = {
    "/": "inicio",
    "/turismo-y-recursos": "turismo-y-recursos",
    "/clima-y-agua": "clima-y-agua",
    "/movilidad": "movilidad",
    "/tiempo-y-entorno": "tiempo-y-entorno",
    "/explorador?source=aemet&metric=temperature_2m_mean&entity=B228&range=five": "explorador",
    "/operacion": "operacion",
}
# Every panel has finished loading: no skeleton or spinner is left.
_LOADED = "document.querySelectorAll('.skeleton, [aria-busy=\"true\"]').length === 0"


def _shoot(page: Page, route: str, path: Path) -> None:
    page.set_viewport_size({"width": WIDTH, "height": 900})
    page.goto(f"{WEB}{route}", wait_until="networkidle")
    page.wait_for_function(_LOADED, timeout=30_000)
    page.wait_for_timeout(1500)
    # The viewport grows to the whole page, so the sticky menu spans it and every chart and map is laid out at its
    # final size. A full-page screenshot would resize the page while it is taken and catch the charts mid-resize.
    page.set_viewport_size({"width": WIDTH, "height": int(page.evaluate("document.documentElement.scrollHeight"))})
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(6000)  # charts redraw and the map tiles arrive
    page.screenshot(path=path)
    print(path.name)  # noqa: T201 - progress of a command-line tool


def main(out_dir: Path) -> None:
    """Write one PNG per dashboard into ``out_dir``, plus the home page in the dark theme."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        # SwiftShader gives the headless browser the WebGL that MapLibre needs.
        browser = playwright.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        for theme in ("light", "dark"):
            page = browser.new_page(color_scheme=theme, locale="es-ES", timezone_id="Europe/Madrid")
            # The theme button stores its choice here; the page reads it before the first paint.
            page.add_init_script(f"localStorage.setItem('mdp-theme', '{theme}')")
            routes = DASHBOARDS if theme == "light" else {"/": "inicio-oscuro"}
            for route, name in routes.items():
                _shoot(page, route, out_dir / f"{name}.png")
            page.close()
        browser.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/img/web"))
