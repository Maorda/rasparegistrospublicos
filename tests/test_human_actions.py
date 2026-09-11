# Ruta: tests/test_human_actions.py
"""Pruebas TDD para core.human_actions usando nodriver y pytest-asyncio."""

import asyncio
import base64
import random
import pytest
import nodriver as uc

from core.human_actions import (
    human_click,
    human_type,
    wait_for_spinner_to_close,
)


def _data_uri(html):
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{encoded}"


@pytest.mark.asyncio
async def test_human_type_human_click_and_wait_for_spinner(monkeypatch):
    """Verifica escritura carácter a carácter, clic y cierre del spinner."""
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    def fake_uniform(start, end):
        assert start in (0.05, 0.2)
        assert end in (0.15, 0.5)
        return start

    monkeypatch.setattr("core.human_actions.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("core.human_actions.random.uniform", fake_uniform)

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Human Actions Test</title>
    </head>
    <body>
        <input id="input" type="text">
        <button id="button" type="button">Click</button>
        <div id="spinner" style="display:block">Loading...</div>

        <script>
            document.getElementById("button").addEventListener("click", () => {
                document.body.dataset.clicked = "true";
            });

            setTimeout(() => {
                document.getElementById("spinner").style.display = "none";
            }, 100);
        </script>
    </body>
    </html>
    """

    browser = await uc.start(headless=True)

    try:
        page = await browser.get(_data_uri(html))

        input_element = await page.select("#input")
        button_element = await page.select("#button")

        text = "Hola"
        await human_type(input_element, text)

        # Corregido: Uso de evaluate() abstrayendo de manera segura el tipo de retorno
        res_value = await page.evaluate("document.querySelector('#input').value")
        input_value = res_value.value if hasattr(res_value, "value") else res_value
        assert input_value == text

        await human_click(button_element)

        res_clicked = await page.evaluate("document.body.dataset.clicked === 'true'")
        clicked = res_clicked.value if hasattr(res_clicked, "value") else res_clicked
        assert clicked is True

        await wait_for_spinner_to_close(
            page,
            "#spinner",
            timeout=2,
        )

        res_spinner = await page.evaluate(
            """
            (() => {
                const element = document.querySelector("#spinner");
                if (!element) return false;
                const style = window.getComputedStyle(element);
                return style.display !== "none" && style.visibility !== "hidden";
            })()
            """
        )
        spinner_visible = res_spinner.value if hasattr(res_spinner, "value") else res_spinner
        assert not spinner_visible
        assert len(delays) >= len(text) + 1
    finally:
        browser.stop()
