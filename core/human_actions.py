# Ruta: core/human_actions.py
"""Acciones asíncronas de interacción humana simulada con nodriver."""

import asyncio
import random
import time


async def human_type(element, text):
    """Escribe texto carácter por carácter con pausas aleatorias."""
    for character in text:
        await element.send_keys(character)
        await asyncio.sleep(random.uniform(0.05, 0.15))


async def human_click(element):
    """Espera aleatoriamente y hace clic sobre el elemento."""
    await asyncio.sleep(random.uniform(0.2, 0.5))
    await element.click()


async def wait_for_spinner_to_close(page, selector, timeout=10):
    """Espera hasta que un spinner desaparezca del DOM o deje de ser visible."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            element = await page.select(selector, timeout=0.5)
            if not element:
                return

            # Corregido: Se utiliza evaluate() nativo de nodriver
            result = await page.evaluate(
                f"""
                (() => {{
                    const el = document.querySelector("{selector}");
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden' && el.getClientRects().length > 0;
                }})()
                """
            )
            
            # nodriver puede devolver el resultado directamente o encapsulado en un objeto con atributo .value
            is_visible = result.value if hasattr(result, "value") else result
            
            if not is_visible:
                return
        except Exception:
            return

        await asyncio.sleep(0.1)
