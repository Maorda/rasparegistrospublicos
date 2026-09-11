# Ruta: flows/download_flow.py
"""Flujo de negocio para descargar PDFs, consolidarlos en un único archivo binario usando fitz y regresar apuntando al ojo de previsualización."""

import asyncio
import glob
import os
import time
import fitz  # PyMuPDF para fusión real y limpia de documentos PDF
import nodriver as uc
from core.human_actions import human_click, wait_for_spinner_to_close


async def safe_rename(src: str, dst: str, retries: int = 10, delay: float = 0.5) -> bool:
    """Intenta renombrar un archivo con reintentos para evitar bloqueos de I/O en Windows (PermissionError)."""
    for _ in range(retries):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)
            return True
        except PermissionError:
            # El navegador todavía tiene el archivo abierto escribiendo los bytes en el disco
            await asyncio.sleep(delay)
        except FileNotFoundError:
            return False
    return False


async def run_download_flow(page: uc.Tab, expediente_str: str) -> None:
    """Ejecuta la descarga secuencial de asientos y los consolida bajo el nombre único 'sunarp_[expediente].pdf'."""
    
    print("[INFO] Localizando el botón del icono del OJO en la columna PREVISUALIZA...")
    btn_search = None
    try:
        btn_search = await page.select('button:has(.anticon-eye), button[title*="Previsualiza"], button.btn-search:not([title*="Resumen"]) i.icon-view', timeout=10.0)
    except asyncio.TimeoutError:
        pass
    
    # Fallback de respaldo estructural por si el DOM de Angular parpadea tras el renderizado
    if not btn_search:
        try:
            btn_search = await page.select('button .anticon-eye', timeout=5.0)
        except asyncio.TimeoutError:
            raise RuntimeError("No se encontró el botón de previsualización (Ojo) en el DOM.")

    # CORREGIDO: Firma de función limpia sin pasar 'page' para evitar un TypeError fulminante
    await human_click(btn_search)
    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=15.0)

    botones_pagina = await page.select_all(".columna-lista .boton-pagina")
    download_dir = os.path.abspath("./downloads")
    os.makedirs(download_dir, exist_ok=True) # Garantizar que la carpeta exista

    # Limpiamos caracteres prohibidos del nombre del expediente para evitar errores en Windows
    safe_expediente = expediente_str.replace("/", "_").replace("\\", "_").replace(":", "_")

    # Nombre final exacto solicitado
    nombre_final_unico = os.path.join(download_dir, f"sunarp_{safe_expediente}.pdf")
    if os.path.exists(nombre_final_unico):
        try:
            os.remove(nombre_final_unico)
        except Exception:
            pass

    archivos_descargados_ciclo = []

    for index, btn_pagina in enumerate(botones_pagina):
        try:
            # Capturamos el estado de la carpeta ANTES (sin incluir descargas previas ni temporales)
            archivos_antes = set(
                f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                if not os.path.basename(f).startswith(("temp_", "sunarp_"))
            )

            # CORREGIDO: Firma de función limpia sin pasar 'page'
            await human_click(btn_pagina)
            await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading, .swal2-loading", timeout=8.0)

            btn_download = await page.select("button#download")
            if btn_download:
                # CORREGIDO: Firma de función limpia sin pasar 'page'
                await human_click(btn_download)
            else:
                print(f"[WARNING] Botón de descarga no encontrado en el asiento {index}.")
                continue

            # Bucle elástico mejorado
            nuevo_archivo = None
            timeout_archivo = time.monotonic() + 15.0
            
            while time.monotonic() < timeout_archivo:
                await asyncio.sleep(0.5)
                # Chrome usa extensiones .crdownload o .tmp mientras descarga.
                # Al filtrar por *.pdf, el archivo solo aparecerá aquí cuando cambie de extensión de forma limpia.
                archivos_despues = set(
                    f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                    if not os.path.basename(f).startswith(("temp_", "sunarp_"))
                )
                
                diferencia = archivos_despues - archivos_antes
                if diferencia:
                    archivo_detectado = list(diferencia)[0]
                    # Verificación doble de estabilidad de escritura
                    if os.path.exists(archivo_detectado) and not archivo_detectado.endswith('.crdownload'):
                        nuevo_archivo = archivo_detectado
                        break

            if nuevo_archivo:
                nombre_temporal_asiento = os.path.join(download_dir, f"temp_{safe_expediente}_{index}.pdf")
                
                # Intentamos renombrar de forma segura (tolerante a bloqueos de Windows)
                renombrado_ok = await safe_rename(nuevo_archivo, nombre_temporal_asiento)
                
                if renombrado_ok:
                    archivos_descargados_ciclo.append(nombre_temporal_asiento)
                else:
                    print(f"[ERROR] No se pudo liberar/renombrar el archivo: {nuevo_archivo}")

        except Exception as e:
            print(f"[WARNING] Percance menor en página del asiento {index}, continuando: {str(e)}")
            continue

    # PROCESO DE CONSOLIDACIÓN AUTOMÁTICA EN UN SOLO PDF ÚNICO
    if archivos_descargados_ciclo:
        print(f"[SISTEMA] Combinando {len(archivos_descargados_ciclo)} asientos descargados bajo el formato final...")

        if len(archivos_descargados_ciclo) == 1:
            await safe_rename(archivos_descargados_ciclo[0], nombre_final_unico)
        else:
            # Fusión real de múltiples PDFs usando PyMuPDF (fitz)
            doc_final = fitz.open()
            for pdf_temp in archivos_descargados_ciclo:
                try:
                    with fitz.open(pdf_temp) as doc_asiento:
                        doc_final.insert_pdf(doc_asiento)
                except Exception as e:
                    print(f"[WARNING] No se pudo anexar el PDF temporal '{pdf_temp}': {str(e)}")

            doc_final.save(nombre_final_unico)
            doc_final.close()

            # Limpieza de archivos temporales individuales
            for temp_file in archivos_descargados_ciclo:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass

        print(f"[SISTEMA] Archivo final guardado perfectamente como: {os.path.basename(nombre_final_unico)}")
    else:
        print("[WARNING] No se descargó ningún asiento exitosamente.")

    print("[INFO] Finalizadas las descargas del expediente. Limpiando foco del visor de PDF...")
    await asyncio.sleep(1.5)
    await page.evaluate("window.focus(); document.body.focus();")
    await asyncio.sleep(0.5)

    print("[INFO] Presionando el botón 'Regresar' oficial para reiniciar los 9 min de sesión...")
    try:
        btn_regresar = await page.select("button.btn-logout", timeout=5.0)
        # CORREGIDO: Firma de función limpia sin pasar 'page'
        await human_click(btn_regresar)
    except asyncio.TimeoutError:
        print("[INFO] Botón regresar no encontrado, forzando retroceso en historial (History Back)...")
        await page.evaluate("window.history.back();")

    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=12.0)
    await asyncio.sleep(1.5)
