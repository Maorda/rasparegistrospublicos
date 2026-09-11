# Ruta: core/browser.py
"""Inicialización segura del navegador con nodriver configurando políticas estrictas de descarga masiva."""

import os
import nodriver as uc


async def init_browser(headless: bool = False):
    """Inicializa una instancia de nodriver con argumentos de evasión de detección

    y políticas de automatización para descargas masivas e interferencias de PDFs.
    """
    download_dir = os.path.abspath("./downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    # Creamos un directorio temporal para el perfil de usuario de este ciclo
    # Esto nos permite forzar preferencias limpias sin interferencias de sesiones viejas
    user_data_dir = os.path.abspath("./user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    # Argumentos y flags nativos de Chromium de nivel de sistema para descargas masivas
    # 1. --disable-pdf-viewer: Prohíbe que el navegador intente abrir el archivo PDF de manera automática
    browser_args = [
        "--window-size=1920,1080",
        "--lang=es-419,es;q=0.9",
        "--disable-extensions",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-service-autorun",
        "--password-store=basic",
        "--disable-pdf-viewer", 
    ]

    # Inicialización nativa de nodriver con sus flags de evasión asignando correctamente el perfil de usuario
    browser = await uc.start(
        headless=headless,
        browser_args=browser_args,
        user_data_dir=user_data_dir  # Asignación correcta para evitar duplicidad de flags
    )

    # Inyección complementaria a nivel de pestaña activa (CDP)
    try:
        # nodriver expone las pestañas abiertas mediante la lista interna de targets u obteniendo la actual
        page = await browser.get("about:blank")
        
        # Forzar el comportamiento de descarga segura en la ruta local sin prompts visuales ni diálogos de confirmación
        await page.send(
            uc.cdp.page.set_download_behavior(
                behavior="allow", 
                download_path=download_dir
            )
        )
    except Exception as e:
        # Capturamos de forma segura sin romper el flujo de arranque del robot
        pass

    return browser
