# Ruta: main.py
"""Orquestador maestro continuo por lotes con bucle elástico de rotación de DNI y re-autenticación blindada."""

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
    """Orquestador principal por lotes implementado como Máquina de Estados para garantizar 
    la rotación continua sin recursividad ni fugas de memoria.
    """
    origen_path = os.path.join("config", "expedientes_origen.json")
    if not os.path.exists(origen_path):
        raise FileNotFoundError(f"No se encontró el archivo: {origen_path}")

    with open(origen_path, "r", encoding="utf-8") as f:
        expedientes_list = json.load(f)

    lote_completado = False

    # =====================================================================
    # BUCLE MAESTRO: Controla la ejecución total sin recursividad
    # =====================================================================
    while not lote_completado:
        browser = None
        active_cred = None

        try:
            # =====================================================================
            # FASE A: BUCLE INTELIGENTE DE AUTENTICACIÓN
            # =====================================================================
            while True:
                try:
                    active_cred = get_active_credential()
                    print(f"\n[SISTEMA] DNI SELECCIONADO PARA AUTENTICACIÓN: {active_cred['nombre_registrado']} (DNI: {active_cred['dni']})")
                    print(f"[SISTEMA] Intentos registrados en JSON local: {active_cred['ingresos_ciclo']}/5")
                except RuntimeError as e:
                    print(f"\n[PROCESO TERMINADO COMPLETO]: {str(e)}")
                    return # Cierre definitivo, no hay más credenciales útiles

                browser = await init_browser(headless=False)
                
                # CORREGIDO: Redirección forzada estricta a la URL oficial de la aplicación
                page = await browser.get("https://conoce-aqui.sunarp.gob.pe/conoce-aqui/inicio")

                try:
                    await run_validation_flow(page, active_cred["dni"], active_cred["digito"], active_cred["fecha_emision"])
                    increment_credential_intents(active_cred["dni"])
                    print(f"[SISTEMA] Autenticación Exitosa con DNI {active_cred['dni']}. Avanzando al procesamiento de lotes...")
                    break # Sale del bucle de autenticación para ir a la Fase B

                except ValueError as ve:
                    if "CUPO_AGOTADO" in str(ve):
                        print(f"\n[ALERT SERVER] El DNI {active_cred['dni']} fue rechazado por el servidor (Cupo Máximo Alcanzado).")
                        print("[SISTEMA] Marcando intentos a 5 de forma forzada en 'config/filtro.json'...")
                        
                        filtro_file = os.path.join("config", "filtro.json")
                        with open(filtro_file, "r+", encoding="utf-8") as f:
                            creds = json.load(f)
                            for c in creds:
                                if str(c["dni"]) == str(active_cred["dni"]):
                                    c["ingresos_ciclo"] = 5
                            f.seek(0)
                            json.dump(creds, f, indent=2, ensure_ascii=False)
                            f.truncate()
                        
                        if browser is not None:
                            browser.stop()
                        await asyncio.sleep(1.5)
                        print("[SISTEMA] Rotando credencial... Saltando al siguiente DNI libre de tu lista.")
                        continue # Reintenta con la siguiente credencial
                    else:
                        raise ve

            # =====================================================================
            # FASE B: PROCESAMIENTO SECUENCIAL DEL LOTE
            # =====================================================================
            await asyncio.sleep(2.0)
            area_registral_default = "PROPIEDAD INMUEBLE PREDIAL"
            sesion_activa = True

            for item in expedientes_list:
                expediente_str = item.get("expediente")
                numero_partida = item.get("numero_partida")
                area_registral_dinamica = item.get("area_registral", area_registral_default)

                print(f"\n[PROCESANDO] Expediente: {expediente_str} | Partida: {numero_partida}")

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

                print("[INFO] Esperando el asentamiento completo del formulario de búsqueda...")
                await asyncio.sleep(3.5)

                filter_data = {
                    "oficina_registral": oficina_nombre,
                    "area_registral": area_registral_dinamica,
                    "partida": "2",
                    "numero": str(numero_partida),
                }

                try:
                    await run_query_flow(page, filter_data)
                    await run_download_flow(page, expediente_str)

                    update_expediente_status(expediente_str, str(numero_partida), "PROCESADO", "Descarga completada con éxito.")
                    print(f"[ÉXITO] Expediente {expediente_str} procesado correctamente.")

                except Exception as e:
                    err_msg = f"Fallo en la interfaz de la SUNARP: {str(e)}"
                    print(f"[ERROR CONTENIDO]: {err_msg}")
                    
                    if "cupo_partida_excedido" in err_msg.lower():
                        print(f"\n[SISTEMA CRÍTICO] El DNI activo {active_cred['dni']} fue blocked para esta partida.")
                        print("[SISTEMA] Inhabilitando DNI actual de forma forzada en 'config/filtro.json'...")
                        
                        filtro_file = os.path.join("config", "filtro.json")
                        with open(filtro_file, "r+", encoding="utf-8") as f:
                            creds = json.load(f)
                            for c in creds:
                                if str(c["dni"]) == str(active_cred["dni"]):
                                    c["ingresos_ciclo"] = 5
                            f.seek(0)
                            json.dump(creds, f, indent=2, ensure_ascii=False)
                            f.truncate()
                        
                        sesion_activa = False
                        print("[SISTEMA] Cerrando sesión actual por bloqueo de partida. Rotando DNI...")
                        break # Rompe el FOR, el BUCLE MAESTRO reiniciará el proceso
                    
                    if any(keyword in err_msg.lower() for keyword in ["timeout", "not find", "could not", "cupo_agotado", "send_keys", "buscar-partida"]):
                        print("\n[SESIÓN INESTABLE / EXPIRADA]. Activando protocolo de re-autenticación en caliente...")
                        sesion_activa = False
                        break # Rompe el FOR, el BUCLE MAESTRO reiniciará el proceso

            # Si el bucle FOR termina naturalmente (sin breaks por caídas de sesión), el lote está completado.
            if sesion_activa:
                lote_completado = True
                print("\n[FINALIZADO] Procesamiento de todos los lotes completado de forma inteligente.")

        except Exception as e:
            print(f"\n[ERROR CRÍTICO MAESTRO]: {str(e)}")
            await asyncio.sleep(2.0)
            
        finally:
            if browser is not None:
                browser.stop()
                await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())
