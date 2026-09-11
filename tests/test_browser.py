# Ruta: tests/test_browser.py
"""Pruebas TDD para la inicialización y ciclo de vida del navegador."""

import pytest
from core.browser import init_browser


@pytest.mark.asyncio
async def test_init_browser_lifecycle():
    """Verifica que el navegador se inicialice, opere y se detenga correctamente."""
    browser = None
    try:
        browser = await init_browser(headless=True)
        assert browser is not None
        # Validamos que sea una instancia operativa comprobando que tenga el método de cierre
        assert hasattr(browser, "stop")

        # Verificación básica de navegación asíncrona
        page = await browser.get("about:blank")
        assert page is not None
    finally:
        if browser is not None:
            # El método stop() en nodriver es síncrono
            browser.stop()
