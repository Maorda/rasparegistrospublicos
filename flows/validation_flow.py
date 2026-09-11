# Ruta: flows/validation_flow.py
"""Flujo de negocio para la fase de validación inicial en la SUNARP con detección exacta del mensaje de cupos de SweetAlert2."""

import asyncio
import random
import time
import nodriver as uc
from core.human_actions import (
    human_click,
    human_type,
    wait_for_spinner_to_close,
)

async def run_validation_flow(page: uc.Tab, dni: str, digito: str, fecha_emision: str) -> None:
    """
    Ejecuta el flujo de validación inicial controlando de forma humana los modales
    de sesión concurrente, errores de captcha y bloqueos por límite diario de la SUNARP.
    """
    print("[INFO] Esperando estabilidad de red y renderizado completo del DOM...")
    try:
        await page.wait_for_page_to_load()
    except Exception:
        await asyncio.sleep(3.0)

    # Paso 1.1: Captura e interacción con el modal de bienvenida inicial
    print("[INFO] Buscando el modal de bienvenida ('Sí Acepto')...")
    await page.wait_for("button.accept-button", timeout=15.0)
    accept_btn = await page.select("button.accept-button")
    await human_click(accept_btn)
    await asyncio.sleep(1.5)

    # Preparación y llenado humano de datos
    dni_input = await page.select('input[formcontrolname="numeroDocumento"]')
    await human_click(dni_input)
    await human_type(dni_input, dni)

    digito_input = await page.select('input[formcontrolname="digito"]')
    await human_click(digito_input)
    await human_type(digito_input, digito)

    fecha_input = await page.select('input[formcontrolname="fechaEmision"]')
    await human_click(fecha_input)
    await human_type(fecha_input, fecha_emision)

    # Intentos de validación con reentrada en caso de salto de error de captcha
    max_intentos_validacion = 3
    for intento in range(max_intentos_validacion):
        print(f"[INFO] Intento de validación {intento + 1}/{max_intentos_validacion}...")
        
        await asyncio.sleep(random.uniform(4.0, 6.0))

        validate_btn = await page.select("button.btn-sunarp-green")
        await human_click(validate_btn)

        # 1. Monitorear e interceptar el modal de sesión concurrente ("Sí, iniciar")
        print("[INFO] Verificando respuestas de validación o modales de la SUNARP...")
        await asyncio.sleep(2.5) # Margen de tiempo para renderizado de SweetAlert2
        
        swal_btn = None
        try:
            swal_btn = await page.select("button.swal2-confirm", timeout=1.0)
        except Exception:
            pass

        if swal_btn:
            # CORREGIDO: Inyección JS segura con fallback de string vacío para evitar excepciones de deserialización
            res_text = await page.evaluate("document.querySelector('button.swal2-confirm')?.innerText || ''")
            btn_text_str = res_text.value if hasattr(res_text, 'value') else res_text
            
            if "iniciar" in str(btn_text_str).lower():
                pausa_captcha = random.uniform(4.0, 6.0)
                print(f"[INFO] Pausa táctica de {pausa_captcha:.2f} segundos para resolución de captcha...")
                await asyncio.sleep(pausa_captcha)
                
                print("[ALERT] Cerrando sesión activa previa presionando 'Sí, iniciar'...")
                await human_click(swal_btn)
                
                print("[INFO] Esperando a que cierre el spinner de la sesión concurrente...")
                await asyncio.sleep(2.0)
                await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading, .swal2-loading", timeout=6.0)

        # 2. Interceptador definitivo del Mensaje de Límite Diario de la SUNARP
        await asyncio.sleep(1.5)
        swal_error_btn = None
        try:
            swal_error_btn = await page.select("button.swal2-confirm", timeout=1.0)
        except Exception:
            pass

        if swal_error_btn:
            # CORREGIDO: Inyección JS segura con fallback de string vacío para evitar excepciones de deserialización
            res_err = await page.evaluate("document.querySelector('button.swal2-confirm')?.innerText || ''")
            err_text_str = res_err.value if hasattr(res_err, 'value') else res_err
            
            if "aceptar" in str(err_text_str).lower():
                modal_html = await page.evaluate("document.querySelector('.swal2-html-container')?.innerText || ''")
                modal_text = modal_html.value if hasattr(modal_html, 'value') else modal_html
                
                print(f"[ALERT SUNARP] Mensaje detectado en pantalla: '{modal_text}'")
                
                # Cerramos el modal presionando el botón 'Aceptar' de forma humana
                print("[INFO] Presionando el botón 'Aceptar' de color turquesa para cerrar el modal...")
                await human_click(swal_error_btn)
                await asyncio.sleep(1.5)

                # CORREGIDO: Filtro estricto basado en el texto real reportado en tu log de consola
                if "mañana" in str(modal_text).lower() or "utilizar" in str(modal_text).lower() or "servicio" in str(modal_text).lower():
                    print("[SISTEMA] Confirmado: Límite máximo diario superado en el servidor para este DNI.")
                    print("[SISTEMA] Lanzando gatillo de rotación inmediata de credenciales...")
                    raise ValueError("CUPO_AGOTADO")
                
                # Si era solo un parpadeo del captcha, dejamos que el bucle reintente de forma regular
                print("[WARNING] Alerta de captcha detectada, reintentando validación del formulario...")
                await asyncio.sleep(2.5)
                continue

        break

    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading")
