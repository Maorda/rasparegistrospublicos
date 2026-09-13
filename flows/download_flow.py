# Ruta: flows/download_flow.py
"""Flujo de negocio para descargar PDFs de forma nativa, consolidarlos en un único archivo por expediente usando PyMuPDF y regresar."""

import asyncio
import glob
import os
import time
import pymupdf  # PyMuPDF para fusión real y limpia de documentos PDF
import nodriver as uc
from core.human_actions import human_click, wait_for_spinner_to_close

async def safe_rename(src: str, dst: str, retries: int = 20, delay: float = 0.5) -> bool:
    """Intenta renombrar un archivo con reintentos ampliados para evitar bloqueos de I/O por Antivirus o Chrome en Windows."""
    for _ in range(retries):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)
            return True
        except PermissionError:
            # El navegador o Windows Defender todavía tiene el archivo abierto/bloqueado
            await asyncio.sleep(delay)
        except FileNotFoundError:
            return False
    return False

async def run_download_flow(page: uc.Tab, expediente_str: str) -> None:
    """Ejecuta la descarga secuencial de asientos y los consolida bajo el nombre único 'sunarp_[expediente].pdf'."""
    
    # 1. Configurar la carpeta de descargas explícitamente en el navegador
    download_dir = os.path.abspath("./downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    # CORREGIDO: Inyección CDP por dominio 'page' oficial y compatible para nodriver
    await page.send(uc.cdp.page.set_download_behavior(
        behavior="allow",
        download_path=download_dir
    ))

    print("[INFO] Localizando el botón del icono del OJO en la columna PREVISUALIZA...")
    btn_search = None
    try:
        btn_search = await page.select('button:has(.anticon-eye), button[title*="Previsualiza"], button.btn-search:not([title*="Resumen"]) i.icon-view', timeout=10.0)
    except asyncio.TimeoutError:
        pass
    
    # Fallback de respaldo estructural
    if not btn_search:
        try:
            btn_search = await page.select('button .anticon-eye', timeout=5.0)
        except asyncio.TimeoutError:
            raise RuntimeError("No se encontró el botón de previsualización (Ojo) en el DOM.")

    await human_click(btn_search)
    await asyncio.sleep(1.5)

    # Interceptador de control de bloqueo
    try:
        swal_error_btn = await page.select("button.swal2-confirm", timeout=1.5)
        if swal_error_btn:
            res_err = await page.evaluate("document.querySelector('button.swal2-confirm')?.innerText || ''")
            err_text_str = res_err.value if hasattr(res_err, "value") else res_err
            
            if "aceptar" in str(err_text_str).lower():
                modal_html = await page.evaluate("document.querySelector('.swal2-html-container')?.innerText || ''")
                modal_text = modal_html.value if hasattr(modal_html, "value") else modal_html
                print(f"[ALERT SUNARP] Mensaje detectado en visualización: '{modal_text}'")
                await human_click(swal_error_btn)
                await asyncio.sleep(1.5)
                raise ValueError("CUPO_PARTIDA_EXCEDIDO")
    except ValueError as ve:
        raise ve
    except Exception:
        pass

    await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=13.0)

    print("[INFO] Esperando el renderizado de la lista de asientos en la barra lateral...")
    try:
        await page.wait_for(".columna-lista", timeout=8.0)
    except Exception:
        await asyncio.sleep(2.0)

    botones_pagina = await page.select_all(".columna-lista .boton-pagina")
    total_asientos = len(botones_pagina)
    
    safe_expediente = expediente_str.replace("/", "_").replace("\\", "_").replace(":", "_")
    nombre_final_unico = os.path.join(download_dir, f"sunarp_{safe_expediente}.pdf")
    
    if os.path.exists(nombre_final_unico):
        try:
            os.remove(nombre_final_unico)
        except Exception:
            pass

    archivos_descargados_ciclo = []

    # Bloque TRY-FINALLY global para asegurar la limpieza de temporales pase lo que pase
    try:
        for index in range(total_asientos):
            try:
                botones_actualizados = await page.select_all(".columna-lista .boton-pagina")
                if index >= len(botones_actualizados):
                    break
                    
                btn_pagina = botones_actualizados[index]
                
                # Estado del disco ANTES
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

                nuevo_archivo = None
                timeout_archivo = time.monotonic() + 15.0
                
                while time.monotonic() < timeout_archivo:
                    await asyncio.sleep(0.5)
                    # Estado del disco DESPUÉS
                    archivos_despues = set(
                        f for f in glob.glob(os.path.join(download_dir, "*.pdf"))
                        if not os.path.basename(f).startswith(("temp_", "sunarp_"))
                    )
                    
                    diferencia = archivos_despues - archivos_antes
                    if diferencia:
                        lista_dif = list(diferencia)
                        # Verificamos si el archivo de verdad existe en disco
                        if lista_dif and os.path.exists(lista_dif[0]):
                            nuevo_archivo = lista_dif[0]
                            break

                if nuevo_archivo:
                    nombre_temporal_asiento = os.path.join(download_dir, f"temp_{safe_expediente}_{index}.pdf")
                    renombrado_ok = await safe_rename(nuevo_archivo, nombre_temporal_asiento)
                    
                    if renombrado_ok:
                        archivos_descargados_ciclo.append(nombre_temporal_asiento)
                    else:
                        print(f"[ERROR] No se pudo liberar el archivo descargado: {nuevo_archivo}")
                else:
                    print(f"[ERROR] Timeout alcanzado (15s) en asiento {index}. Descarga incompleta.")

            except Exception as e:
                print(f"[WARNING] Percance menor en página del asiento {index}, continuando: {str(e)}")
                continue

        # =========================================================================
        # FASE DE CONSOLIDACIÓN AUTOMÁTICA BINARIA REAL (MERGE PDF)
        # =========================================================================
        if archivos_descargados_ciclo:
            print(f"[SISTEMA] Combinando exitosamente {len(archivos_descargados_ciclo)} asientos...")

            if len(archivos_descargados_ciclo) == 1:
                await safe_rename(archivos_descargados_ciclo[0], nombre_final_unico)
            else:
                doc_final = pymupdf.open()
                for pdf_temp in archivos_descargados_ciclo:
                    try:
                        # Prevenimos intentar abrir archivos con 0 bytes si la descarga falló
                        if os.path.getsize(pdf_temp) > 0:
                            with pymupdf.open(pdf_temp) as doc_asiento:
                                doc_final.insert_pdf(doc_asiento)
                        else:
                            print(f"[WARNING] Archivo temporal vacío omitido: {pdf_temp}")
                    except Exception as e:
                        print(f"[WARNING] No se pudo anexar el PDF temporal '{pdf_temp}': {str(e)}")

                doc_final.save(nombre_final_unico)
                doc_final.close()

            print(f"[SISTEMA] Archivo final unificado guardado perfectamente como: {os.path.basename(nombre_final_unico)}")
        else:
            print("[WARNING] No se recopiló ningún asiento exitosamente para este expediente.")

    finally:
        # Esto garantiza que los archivos temporales se borren INCLUSO si hay un error en PyMuPDF o el bucle
        for temp_file in archivos_descargados_ciclo:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    print("[INFO] Finalizadas las descargas del expediente. Limpiando foco del visor...")
    await asyncio.sleep(1.0)
    await page.evaluate("window.focus(); document.body.focus();")

    print("[INFO] Presionando el botón 'Regresar'...")
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
