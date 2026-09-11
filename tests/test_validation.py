# Ruta: tests/test_validation.py
"""Pruebas TDD para el flujo de validación de SUNARP."""

import base64
import pytest
import nodriver as uc
from flows.validation_flow import run_validation_flow

HTML_FORM_CONTENT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Formulario Test SUNARP</title>
</head>
<body>
    <button class="accept-button">Sí Acepto</button>
    
    <form>
        <input formcontrolname="numeroDocumento" type="text" id="dni" />
        <input formcontrolname="digito" type="text" id="digito" />
        <input formcontrolname="fechaEmision" type="text" id="fecha" />
        <button class="btn-sunarp-green" type="button">Validar</button>
    </form>

    <div class="ant-spin ant-spin-spinning" id="spinner" style="display:none;"></div>

    <script>
        const btnValidate = document.querySelector('.btn-sunarp-green');
        const spinner = document.getElementById('spinner');

        btnValidate.addEventListener('click', () => {
            spinner.style.display = 'block';
            setTimeout(() => {
                spinner.style.display = 'none';
            }, 100);
        });
    </script>
</body>
</html>
"""

def _data_uri(html):
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{encoded}"

@pytest.mark.asyncio
async def test_run_validation_flow():
    """Valida la inyección correcta de datos de DNI, Dígito y Fecha en el flujo."""
    browser = None
    try:
        browser = await uc.start(headless=True)
        # Corregido: Uso de Data URI compatible con nodriver para inyectar el HTML real
        page = await browser.get(_data_uri(HTML_FORM_CONTENT))

        test_dni = "12345678"
        test_digito = "9"
        test_fecha = "01/01/2020"

        # Ejecución del flujo bajo revisión
        await run_validation_flow(
            page=page,
            dni=test_dni,
            digito=test_digito,
            fecha_emision=test_fecha
        )

        # Extracción y aserción segura de los estados del DOM post-tipeo
        res_dni = await page.evaluate('document.querySelector(\'input[formcontrolname="numeroDocumento"]\').value')
        dni_val = res_dni.value if hasattr(res_dni, "value") else res_dni

        res_digito = await page.evaluate('document.querySelector(\'input[formcontrolname="digito"]\').value')
        digito_val = res_digito.value if hasattr(res_digito, "value") else res_digito

        res_fecha = await page.evaluate('document.querySelector(\'input[formcontrolname="fechaEmision"]\').value')
        fecha_val = res_fecha.value if hasattr(res_fecha, "value") else res_fecha

        assert dni_val == test_dni
        assert digito_val == test_digito
        assert fecha_val == test_fecha

    finally:
        if browser is not None:
            browser.stop()
