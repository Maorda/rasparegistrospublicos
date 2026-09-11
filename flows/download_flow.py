# Ruta: flows/download_flow.py
"""Flujo de negocio para descargar PDFs, consolidarlos en un único archivo binario usando fitz y regresar."""

import asyncio
import glob
import os
import time
import fitz  # PyMuPDF para fusión real y limpia de documentos PDF
import nodriver as uc
from core.human_actions import human_click, wait_for_spinner_to_close


async def run_download_flow(page: uc.Tab, expediente_str: str) -> None:
    """Ejecuta la descarga secuencial de asientos y los consolida bajo el nombre único 'sunarp_[expediente].pdf'."""
    btn_search = await page.select("button.btn-search")
    # CORREGIDO: Firma de función limpia sin pasar 'page'
    await human_click(btn_search)
    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=15.0)

    botones_pagina = await page.select_all(".columna-lista .boton-pagina")
    download_dir = os.path.abspath("./downloads")

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
            # Capturamos el estado de la carpeta antes de accionar la descarga (excluyendo temporales previos)
            archivos_antes = set(
                f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                if not os.path.basename(f).startswith(("temp_", "sunarp_"))
            )

            # CORREGIDO: Firma de función limpia sin pasar 'page'
            await human_click(btn_pagina)
            await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading, .swal2-loading", timeout=8.0)

            btn_download = await page.select("button#download")
            # CORREGIDO: Firma de función limpia sin pasar 'page'
            await human_click(btn_download)

            # Esperamos de forma elástica a que aparezca el nuevo archivo PDF descargado por Chrome
            nuevo_archivo = None
            timeout_archivo = time.monotonic() + 12.0
            while time.monotonic() < timeout_archivo:
                await asyncio.sleep(0.5)
                archivos_despues = set(
                    f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                    if not os.path.basename(f).startswith(("temp_", "sunarp_"))
                )
                diferencia = archivos_despues - archivos_antes
                if diferencia:
                    lista_dif = list(diferencia)
                    # CORREGIDO: Evaluación de extensión segura apuntando al índice 0 de la lista
                    if lista_dif and not lista_dif[0].endswith(".crdownload") and os.path.exists(lista_dif[0]):
                        nuevo_archivo = lista_dif[0]
                        break

            if nuevo_archivo:
                # Guardamos la ruta temporal del asiento descargado para consolidarlo al final
                nombre_temporal_asiento = os.path.join(download_dir, f"temp_{safe_expediente}_{index}.pdf")
                if os.path.exists(nombre_temporal_asiento):
                    os.remove(nombre_temporal_asiento)
                os.rename(nuevo_archivo, nombre_temporal_asiento)
                archivos_descargados_ciclo.append(nombre_temporal_asiento)

        except Exception as e:
            print(f"[WARNING] Percance menor en página del asiento, continuando: {str(e)}")
            continue

    # PROCESO DE CONSOLIDACIÓN AUTOMÁTICA EN UN SOLO PDF ÚNICO
    if archivos_descargados_ciclo:
        print(f"[SISTEMA] Combinando {len(archivos_descargados_ciclo)} asientos descargados bajo el formato final...")

        if len(archivos_descargados_ciclo) == 1:
            os.rename(archivos_descargados_ciclo[0], nombre_final_unico)
        else:
            # Fusión real de múltiples PDFs usando PyMuPDF
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

    print("[INFO] Finalizadas las descargas del expediente. Limpiando foco del visor de PDF...")
    await asyncio.sleep(1.5)
    await page.evaluate("window.focus(); document.body.focus();")
    await asyncio.sleep(0.5)

    print("[INFO] Presionando el botón 'Regresar' oficial para reiniciar los 9 min de sesión...")
    btn_regresar = await page.select("button.btn-logout", timeout=5.0)

    if btn_regresar:
        # CORREGIDO: Firma de función limpia sin pasar 'page'
        await human_click(btn_regresar)
    else:
        await page.evaluate("window.history.back();")

    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=12.0)
    await asyncio.sleep(1.5)
