# Ruta: main.py
"""Orquestador maestro continuo por lotes con bucle elástico de rotación de DNI y control de cupos de la SUNARP."""

import asyncio
import json
import os
from core.browser import init_browser
from flows.validation_flow import run_validation_flow
from flows.query_flow import run_query_flow
from flows.download_flow import run_download_flow
from core.data_manager import (
    get_oficina_by_expediente,
    check_expediente_status,
    update_expediente_status,
    get_active_credential,
    increment_credential_intents,
)


async def main() -> None:
    """Orquestador principal por lotes que procesa los expedientes garantizando

    la rotación continua e indefinida de credenciales DNI quemadas en el servidor.
    """
    origen_path = os.path.join("config", "expedientes_origen.json")
    if not os.path.exists(origen_path):
        raise FileNotFoundError(f"No se encontró el archivo: {origen_path}")

    with open(origen_path, "r", encoding="utf-8") as f:
        expedientes_list = json.load(f)

    browser = None
    active_cred = None

    try:
        # =====================================================================
        # FASE A: BUCLE INTELIGENTE DE AUTENTICACIÓN Y CONTROL DE CUPOS DIARIOS
        # =====================================================================
        while True:
            try:
                # Extrae el primer DNI disponible de la lista con menos de 5 ingresos
                active_cred = get_active_credential()
                print(f"\n[SISTEMA] DNI SELECCIONADO PARA AUTENTICACIÓN: {active_cred['nombre_registrado']} (DNI: {active_cred['dni']})")
                print(f"[SISTEMA] Intentos registrados en JSON local: {active_cred['ingresos_ciclo']}/5")
            except RuntimeError as e:
                print(f"\n[PROCESO TERMINADO COMPLETO]: {str(e)}")
                return

            # Inicializamos una instancia limpia del navegador por cada reintento de credencial
            browser = await init_browser(headless=False)
            
            # CORREGIDO: Redirección forzada estricta a la URL real de la aplicación web
            page = await browser.get("https://conoce-aqui.sunarp.gob.pe/conoce-aqui/inicio")

            try:
                # Intentamos la validación humana simulada ante Cloudflare
                await run_validation_flow(page, active_cred["dni"], active_cred["digito"], active_cred["fecha_emision"])
                
                # Si pasa sin excepciones, el DNI es válido y tiene cupos reales en el servidor.
                # Incrementamos sus intentos en filtro.json y rompemos el bucle para avanzar a los lotes.
                increment_credential_intents(active_cred["dni"])
                print(f"[SISTEMA] Autenticación Exitosa con DNI {active_cred['dni']}. Avanzando al procesamiento de lotes...")
                break

            except ValueError as ve:
                # Capturamos la señal del modal turquesa ('Mañana podrá volver a utilizar nuestro servicio...')
                if "CUPO_AGOTADO" in str(ve):
                    print(f"\n[ALERT SERVER] El DNI {active_cred['dni']} fue rechazado por el servidor (Cupo Máximo Alcanzado).")
                    print("[SISTEMA] Marcando intentos a 5 de forma forzada en 'config/filtro.json'...")
                    
                    # Forzamos la actualización inmediata del JSON local para inhabilitar este DNI
                    filtro_file = os.path.join("config", "filtro.json")
                    with open(filtro_file, "r+", encoding="utf-8") as f:
                        creds = json.load(f)
                        for c in creds:
                            if str(c["dni"]) == str(active_cred["dni"]):
                                c["ingresos_ciclo"] = 5
                        f.seek(0)
                        json.dump(creds, f, indent=2, ensure_ascii=False)
                        f.truncate()
                    
                    # Cierre limpio del navegador para limpiar la caché de sesión corrupta antes de la reentrada
                    if browser is not None:
                        browser.stop()
                    await asyncio.sleep(1.5)
                    print("[SISTEMA] Rotando credencial... Saltando al siguiente DNI libre de tu lista.")
                    continue  # Reinicia el bucle 'while True' de forma inmediata con el navegador limpio
                else:
                    raise ve

        # =====================================================================
        # FASE B: BUCLE SECUENCIAL DE DESCARGAS MASIVAS CONTINUAS
        # =====================================================================
        await asyncio.sleep(2.0)
        area_registral_default = "PROPIEDAD INMUEBLE PREDIAL"

        for item in expedientes_list:
            expediente_str = item.get("expediente")
            numero_partida = item.get("numero_partida")
            area_registral_dinamica = item.get("area_registral", area_registral_default)

            print(f"\n[PROCESANDO] Expediente: {expediente_str} | Partida: {numero_partida}")

            # Pausa obligatoria para el redibujado elástico del DOM tras presionar 'Regresar'
            print("[INFO] Esperando el asentamiento completo del formulario de búsqueda...")
            await asyncio.sleep(3.5)

            if check_expediente_status(expediente_str):
                print(f"[OMITIDO] El expediente {expediente_str} ya se encuentra PROCESADO.")
                continue

            try:
                oficina_nombre = get_oficina_by_expediente(expediente_str)
            except Exception as e:
                err_msg = f"Error al resolver oficina registral: {str(e)}"
                print(f"[ERROR] {err_msg}")
                update_expediente_status(expediente_str, str(numero_partida), "ERROR", err_msg)
                continue

            filter_data = {
                "oficina_registral": oficina_nombre,
                "area_registral": area_registral_dinamica,
                "partida": "2",
                "numero": str(numero_partida),
            }

            try:
                # Inyección JS pura certificada y descargas PyMuPDF compactas
                await run_query_flow(page, filter_data)
                await run_download_flow(page, expediente_str)

                update_expediente_status(expediente_str, str(numero_partida), "PROCESADO", "Descarga completada con éxito.")
                print(f"[ÉXITO] Expediente {expediente_str} procesado correctamente.")

            except Exception as e:
                err_msg = f"Fallo en la interfaz de la SUNARP: {str(e)}"
                print(f"[ERROR CONTENIDO]: {err_msg}")
                update_expediente_status(expediente_str, str(numero_partida), "ERROR", err_msg)
                
                # MANEJO DE CAÍDA DE SESIÓN EN PRODUCCIÓN (Si la sesión caduca a los 9 min a mitad del lote)
                if "timeout" in err_msg.lower() or "not find" in err_msg.lower() or "could not" in err_msg.lower() or "cupo_agotado" in err_msg.lower():
                    print("\n[SESIÓN INESTABLE / EXPIRADA]. Activando protocolo de rotación en caliente...")
                    if browser is not None:
                        browser.stop()
                    await asyncio.sleep(1.5)
                    
                    # Relanzamos de forma segura la función maestra recursiva con el navegador limpio
                    await main()
                    return

        print("\n[FINALIZADO] Procesamiento de todos los lotes completado de forma inteligente.")

    except Exception as e:
        print(f"\n[ERROR CRÍTICO MAESTRO]: {str(e)}")
    finally:
        if browser is not None:
            browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
