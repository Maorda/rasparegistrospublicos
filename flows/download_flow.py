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

    # Firma de función limpia según el core del usuario
    await human_click(btn_search)
    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=15.0)

    print("[INFO] Esperando el renderizado de la lista de asientos en la barra lateral...")
    try:
        await page.wait_for(".columna-lista", timeout=8.0)
    except Exception:
        await asyncio.sleep(2.0)

    # Obtenemos la cantidad de botones para iterar (evita guardar los nodos en memoria para prevenir Stale Elements)
    botones_pagina = await page.select_all(".columna-lista .boton-pagina")
    total_asientos = len(botones_pagina)
    
    download_dir = os.path.abspath("./downloads")
    os.makedirs(download_dir, exist_ok=True)

    safe_expediente = expediente_str.replace("/", "_").replace("\\", "_").replace(":", "_")
    nombre_final_unico = os.path.join(download_dir, f"sunarp_{safe_expediente}.pdf")
    
    if os.path.exists(nombre_final_unico):
        try:
            os.remove(nombre_final_unico)
        except Exception:
            pass

    archivos_descargados_ciclo = []

    for index in range(total_asientos):
        try:
            # Recapturamos dinámicamente el botón para evitar que Angular rompa la referencia DOM
            botones_actualizados = await page.select_all(".columna-lista .boton-pagina")
            if index >= len(botones_actualizados):
                print(f"[WARNING] El asiento índice {index} desapareció del DOM inesperadamente.")
                break
                
            btn_pagina = botones_actualizados[index]
            
            # Estado del directorio ANTES de la descarga
            archivos_antes = set(
                f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                if not os.path.basename(f).startswith(("temp_", "sunarp_"))
            )

            await human_click(btn_pagina)
            await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading, .swal2-loading", timeout=8.0)

            btn_download = await page.select("button#download")
            if btn_download:
                await human_click(btn_download)
            else:
                print(f"[WARNING] Botón de descarga no encontrado en el asiento {index}.")
                continue

            # Bucle elástico de monitoreo de archivos
            nuevo_archivo = None
            timeout_archivo = time.monotonic() + 15.0
            
            while time.monotonic() < timeout_archivo:
                await asyncio.sleep(0.5)
                # Solo captura PDFs finalizados. Chrome elimina la extensión .crdownload al terminar.
                archivos_despues = set(
                    f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                    if not os.path.basename(f).startswith(("temp_", "sunarp_"))
                )
                
                diferencia = archivos_despues - archivos_antes
                # CORREGIDO: Desempaquetado seguro protegiendo la conversión contra IndexError
                if diferencia:
                    lista_dif = list(diferencia)
                    if lista_dif and os.path.exists(lista_dif[0]):
                        nuevo_archivo = lista_dif[0]
                        break  # Archivo PDF detectado de forma exitosa

            if nuevo_archivo:
                nombre_temporal_asiento = os.path.join(download_dir, f"temp_{safe_expediente}_{index}.pdf")
                renombrado_ok = await safe_rename(nuevo_archivo, nombre_temporal_asiento)
                
                if renombrado_ok:
                    archivos_descargados_ciclo.append(nombre_temporal_asiento)
                else:
                    print(f"[ERROR] No se pudo liberar/renombrar el archivo: {nuevo_archivo}")
            else:
                print(f"[ERROR] Timeout agotado (15s). Chrome no terminó de descargar el asiento {index}.")

        except Exception as e:
            print(f"[WARNING] Percance menor en página del asiento {index}, continuando: {str(e)}")
            continue

    # PROCESO DE CONSOLIDACIÓN AUTOMÁTICA
    if archivos_descargados_ciclo:
        print(f"[SISTEMA] Combinando {len(archivos_descargados_ciclo)} asientos descargados...")

        if len(archivos_descargados_ciclo) == 1:
            await safe_rename(archivos_descargados_ciclo[0], nombre_final_unico)
        else:
            doc_final = fitz.open()
            for pdf_temp in archivos_descargados_ciclo:
                try:
                    with fitz.open(pdf_temp) as doc_asiento:
                        doc_final.insert_pdf(doc_asiento)
                except Exception as e:
                    print(f"[WARNING] No se pudo anexar el PDF temporal '{pdf_temp}': {str(e)}")

            doc_final.save(nombre_final_unico)
            doc_final.close()

            for temp_file in archivos_descargados_ciclo:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass

        print(f"[SISTEMA] Archivo final guardado perfectamente como: {os.path.basename(nombre_final_unico)}")
    else:
        print("[WARNING] No se descargó ningún asiento exitosamente.")

    print("[INFO] Finalizadas las descargas. Limpiando foco del visor de PDF...")
    await asyncio.sleep(1.5)
    await page.evaluate("window.focus(); document.body.focus();")
    await asyncio.sleep(0.5)

    print("[INFO] Presionando el botón 'Regresar' oficial...")
    try:
        btn_regresar = await page.select("button.btn-logout", timeout=5.0)
        if btn_regresar:
            await human_click(btn_regresar)
        else:
            raise ValueError("Selector devolvió None")
    except (asyncio.TimeoutError, ValueError):
        print("[INFO] Botón regresar no encontrado, forzando retroceso (History Back)...")
        await page.evaluate("window.history.back();")

    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=12.0)
    await asyncio.sleep(1.5)
