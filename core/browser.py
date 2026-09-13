# Ruta: core/browser.py
"""Inicialización segura del navegador con nodriver configurando políticas estrictas de descarga masiva."""

import os
import json
import logging
import nodriver as uc

logger = logging.getLogger(__name__)

async def init_browser(headless: bool = False):
    """Inicializa una instancia de nodriver con argumentos de evasión de detección

    y políticas de automatización para descargas masivas, libre del aviso de restauración de pestañas.
    """
    download_dir = os.path.abspath("./downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    # Creamos un directorio para el perfil de usuario de este ciclo
    user_data_dir = os.path.abspath("./user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    # Reescritura preventiva del estado de salida en el archivo de preferencias de Chrome
    # Esto le indica a Chromium que la sesión anterior concluyó de manera limpia, eliminando el aviso de restauración.
    pref_dir = os.path.join(user_data_dir, "Default")
    os.makedirs(pref_dir, exist_ok=True)
    pref_path = os.path.join(pref_dir, "Preferences")
    
    if os.path.exists(pref_path):
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            
            if "profile" not in prefs:
                prefs["profile"] = {}
            prefs["profile"]["exit_type"] = "Normal"
            prefs["profile"]["exited_cleanly"] = True
            
            with open(pref_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f)
        except Exception as e:
            logger.warning(f"No se pudieron actualizar las preferencias de Chrome: {e}")

    # Flags nativos de Chromium de nivel de sistema para descargas masivas e inmunidad absoluta de alertas
    # 1. --disable-pdf-viewer: Prohíbe que el navegador intente abrir el archivo PDF de manera automática.
    # 2. --disable-session-crashed-bubble: Destruye e ignora por completo el cartel de 'Restaurar pestañas'.
    # 3. --restore-last-session=false: Prohíbe la recuperación automática de historiales caídos.
    browser_args = [
        "--window-size=1920,1080",
        "--lang=es-419,es;q=0.9",
        "--disable-extensions",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-service-autorun",
        "--password-store=basic",
        "--disable-pdf-viewer", 
        "--disable-session-crashed-bubble",
        "--restore-last-session=false"
    ]

    # Inicialización nativa de nodriver asignando correctamente el perfil de usuario saneado
    browser = await uc.start(
        headless=headless,
        browser_args=browser_args,
        user_data_dir=user_data_dir
    )

    # Inyección complementaria a nivel de CDP para el control de descargas masivas en la ruta local
    try:
        page = await browser.get("about:blank")
        
        # RESTAURADO: Uso del dominio 'page' oficial y compatible que pasó con éxito la suite de pruebas unitarias
        await page.send(
            uc.cdp.page.set_download_behavior(
                behavior="allow",
                download_path=download_dir
            )
        )
    except Exception as e:
        logger.error(f"Error al configurar el comportamiento de descarga por CDP: {e}")

    return browser
