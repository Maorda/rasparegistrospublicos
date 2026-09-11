# Ruta: tests/test_query.py
"""Pruebas TDD para el flujo de filtros de consulta de SUNARP."""

import base64
import pytest
import nodriver as uc
from flows.query_flow import run_query_flow

HTML_QUERY_CONTENT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Consulta Test SUNARP</title>
</head>
<body>
    <div class="ng-tns-c55-8">
        <input class="ant-select-selection-search-input" id="oficina" type="text" />
    </div>

    <div class="ng-tns-c55-10">
        <input class="ant-select-selection-search-input" id="area" type="text" />
    </div>

    <nz-radio-group>
        <label class="ant-radio-wrapper" nzvalue="1" id="label_ficha">
            <input type="radio" name="tipo" value="1" /> Ficha
        </label>
        <label class="ant-radio-wrapper" nzvalue="2" id="label_partida">
            <input type="radio" name="tipo" value="2" id="radio_partida" /> Partida
        </label>
    </nz-radio-group>

    <form>
        <input formcontrolname="numero" type="text" id="numero_partida" />
        <button class="btn-buscar-partida" type="button" id="btn_buscar">Buscar</button>
    </form>

    <script>
        const labelPartida = document.getElementById('label_partida');
        const radioPartida = document.getElementById('radio_partida');
        
        labelPartida.addEventListener('click', () => {
            radioPartida.checked = true;
            labelPartida.dataset.clicked = 'true';
        });

        const oficinaInput = document.getElementById('oficina');
        oficinaInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                oficinaInput.dataset.submitted = 'true';
            }
        });

        const areaInput = document.getElementById('area');
        areaInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                areaInput.dataset.submitted = 'true';
            }
        });

        const btnBuscar = document.getElementById('btn_buscar');
        btnBuscar.addEventListener('click', () => {
            btnBuscar.dataset.clicked = 'true';
        });
    </script>
</body>
</html>
"""

def _data_uri(html):
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{encoded}"

@pytest.mark.asyncio
async def test_run_query_flow():
    """Valida la inyección e interacción asíncrona sobre los componentes de consulta."""
    browser = None
    try:
        browser = await uc.start(headless=True)
        page = await browser.get(_data_uri(HTML_QUERY_CONTENT))

        filter_data = {
            "oficina_registral": "LIMA",
            "area_registral": "PROPIEDAD INMUEBLE",
            "partida": "2",
            "numero": "12345678"
        }

        # Ejecución del flujo dinámico de filtros
        await run_query_flow(page, filter_data)

        # Extracciones seguras evaluando los estados post-evento
        res_oficina = await page.evaluate('document.getElementById("oficina").value')
        oficina_val = res_oficina.value if hasattr(res_oficina, "value") else res_oficina

        res_area = await page.evaluate('document.getElementById("area").value')
        area_val = res_area.value if hasattr(res_area, "value") else res_area

        res_checked = await page.evaluate('document.getElementById("radio_partida").checked')
        radio_checked = res_checked.value if hasattr(res_checked, "value") else res_checked

        res_numero = await page.evaluate('document.getElementById("numero_partida").value')
        numero_val = res_numero.value if hasattr(res_numero, "value") else res_numero

        res_clicked = await page.evaluate('document.getElementById("btn_buscar").dataset.clicked === "true"')
        btn_clicked = res_clicked.value if hasattr(res_clicked, "value") else res_clicked

        # Aserciones de validación TDD
        assert oficina_val == "LIMA"
        assert area_val == "PROPIEDAD INMUEBLE"
        assert radio_checked is True
        assert numero_val == "12345678"
        assert btn_clicked is True

    finally:
        if browser is not None:
            browser.stop()
