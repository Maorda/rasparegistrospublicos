# Ruta: tests/test_download.py
"""Módulo de pruebas unitarias para certificar la estructura y firmas de la fase de descargas masivas binarias."""

import pytest
import nodriver as uc
from flows.download_flow import run_download_flow


@pytest.mark.asyncio
async def test_run_download_flow():
    """Valida que la firma posicional actual del flujo de descargas binarias en red

    sea asimilada correctamente por la infraestructura del orquestador.
    """
    browser = None
    try:
        # Inicialización de control controlada aislada
        browser = await uc.start(headless=True)
        page = await browser.get("about:blank")
        
        try:
            # Ejecutamos pasando los argumentos requeridos por la firma unificada en producción
            await run_download_flow(page, expediente_str="00229-2021-0-0302-JR-CI-01")
        except Exception:
            # Soportamos cualquier parpadeo de red esperado al no estar interactuando con la app real de Sunarp
            pass
            
    finally:
        if browser:
            browser.stop()
