# Ruta: tests/test_download.py
"""Pruebas TDD para el flujo de inspección y descarga secuencial de PDFs de SUNARP."""

import base64
import json
import pytest
import nodriver as uc
from flows.download_flow import run_download_flow

HTML_DOWNLOAD_CONTENT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Visor Descarga Test SUNARP</title>
</head>
<body>
    <button class="btn-search" id="btn_search">Ver Detalle</button>

    <div id="spinner" class="ant-spin ant-spin-spinning" style="display:none;"></div>

    <div class="sidebar">
        <div class="columna-lista">
            <button class="boton-pagina" data-page="1">Página 1</button>
            <button class="boton-pagina" data-page="2">Página 2</button>
        </div>
        <div class="columna-lista">
            <button class="boton-pagina" data-page="3">Página 3</button>
        </div>
    </div>

    <ngx-extended-pdf-viewer>
        <button id="download">Descargar PDF</button>
    </ngx-extended-pdf-viewer>

    <script>
        const clicks = {
            pagesClicked: [],
            downloadClicks: 0,
            searchClicked: false
        };

        const btnSearch = document.getElementById('btn_search');
        btnSearch.addEventListener('click', () => {
            clicks.searchClicked = true;
        });

        const pageBtns = document.querySelectorAll('.columna-lista .boton-pagina');
        pageBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                clicks.pagesClicked.push(btn.getAttribute('data-page'));
            });
        });

        const btnDownload = document.getElementById('download');
        btnDownload.addEventListener('click', () => {
            clicks.downloadClicks++;
        });

        window.getTracker = () => JSON.stringify(clicks);
    </script>
</body>
</html>
"""

def _data_uri(html):
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{encoded}"

@pytest.mark.asyncio
async def test_run_download_flow():
    """Valida la navegación asíncrona, el control de spinners y la descarga masiva."""
    browser = None
    try:
        browser = await uc.start(headless=True)
        page = await browser.get(_data_uri(HTML_DOWNLOAD_CONTENT))

        # Ejecución del flujo bajo revisión TDD
        await run_download_flow(page)

        # Corregido: Forzamos la devolución como un String JSON desde la web y lo parseamos en Python
        # Esto elimina cualquier ambigüedad en la deserialización interna de nodriver
        res_tracker = await page.evaluate("window.getTracker()")
        raw_data = res_tracker.value if hasattr(res_tracker, "value") else res_tracker
        
        tracker = json.loads(raw_data)

        # Aserciones definitivas y seguras
        assert tracker["searchClicked"] is True
        assert tracker["pagesClicked"] == ["1", "2", "3"]
        assert tracker["downloadClicks"] == 3

    finally:
        if browser is not None:
            browser.stop()
