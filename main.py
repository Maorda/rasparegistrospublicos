# Ruta: main.py
"""Orquestador maestro continuo por lotes implementado como Máquina de Estados.

Garantiza la rotación de DNI sin recursividad, control de cortafuegos de errores,
y streaming de bytes binarios en tiempo real directo hacia tu ingestador backend.
"""

import asyncio
import json
import os
import httpx  # Cliente HTTP asíncrono para transmisión directa de bytes
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
    force_disable_credential  # Importación limpia y centralizada
)

async def main() -> None:
    """Orquestador principal por lotes implementado como Máquina de Estados para garantizar 
    la rotación continua sin recursividad ni fugas de memoria en el servidor.
    """
    ENDPOINT_INGESTADOR = "http://tu-servidor-ingestador/api/v1/ingestar-pdf"
    
    origen_path = os.path.join("config", "expedientes_origen.json")
    if not os.path.exists(origen_path):
        raise FileNotFoundError(f"No se encontró el archivo: {origen_path}")

    with open(origen_path, "r", encoding="utf-8") as f:
        expedientes_list = json.load(f)

    lote_completado = False
    errores_criticos_consecutivos = 0  # Cortafuegos de seguridad para evitar bucles infinitos por caídas de red

    # =====================================================================
    # BUCLE MAESTRO: Controla la ejecución total de la Máquina de Estados
    # =====================================================================
    while not lote_completado:
        if errores_criticos_consecutivos >= 3:
            print("\n[ALERTA FATAL] Demasiados errores críticos consecutivos de red o backend. Deteniendo orquestador por seguridad.")
            break

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
                    return  # Cierre definitivo ordinario, no hay más credenciales útiles con cupos libres

                # Levantamos una instancia monousuario limpia desplazada fuera de pantalla
                browser = await init_browser(headless=False)
                
                # CORREGIDO: CONDICIÓN BASE FIJA APLICADA - URL oficial e invariable de arranque
                page = await browser.get("https://conoce-aqui.sunarp.gob.pe/conoce-aqui/inicio")

                try:
                    await run_validation_flow(page, active_cred["dni"], active_cred["digito"], active_cred["fecha_emision"])
                    increment_credential_intents(active_cred["dni"])
                    print(f"[SISTEMA] Autenticación Exitosa con DNI {active_cred['dni']}. Avanzando al procesamiento de lotes...")
                    break  # Sale con éxito del bucle de login para avanzar a la Fase B

                except ValueError as ve:
                    if "CUPO_AGOTADO" in str(ve):
                        print(f"\n[ALERT SERVER] El DNI {active_cred['dni']} fue rechazado por el servidor (Cupo Máximo Alcanzado).")
                        print("[SISTEMA] Inhabilitando DNI actual de forma forzada en el JSON...")
                        
                        force_disable_credential(active_cred["dni"])  # Uso de la función limpia e integrada
                        
                        if browser is not None:
                            browser.stop()
                        await asyncio.sleep(1.5)
                        print("[SISTEMA] Rotando credencial... Saltando al siguiente DNI de la lista.")
                        continue
                    else:
                        raise ve

            # =====================================================================
            # FASE B: PROCESAMIENTO SECUENCIAL DEL LOTE CON STREAMING DIRECTO
            # =====================================================================
            await asyncio.sleep(2.0)
            area_registral_default = "PROPIEDAD INMUEBLE PREDIAL"
            sesion_activa = True
            errores_criticos_consecutivos = 0  # Reseteamos el cortafuegos al loguearnos con éxito

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
                    
                    # El flujo de descargas extrae y unifica todas las páginas directamente en RAM
                    bytes_pdf_consolidado = await run_download_flow(page, expediente_str)

                    # TUBERÍA DE STREAMING BINARIO HACIA TU BACKEND
                    if bytes_pdf_consolidado and len(bytes_pdf_consolidado) > 0:
                        print(f"[INGESTADOR] Iniciando streaming de bytes en caliente hacia el ingestador... ({len(bytes_pdf_consolidado)} bytes)")
                        
                        safe_expediente = expediente_str.replace("/", "_").replace("\\", "_").replace(":", "_")
                        
                        # Empaquetamos el payload binario multipart
                        files = {
                            "file": (f"sunarp_{safe_expediente}.pdf", bytes_pdf_consolidado, "application/pdf")
                        }
                        data = {
                            "expediente": expediente_str,
                            "partida": str(numero_partida)
                        }

                        # Despachamos el stream binario asíncronamente
                        async with httpx.AsyncClient() as client:
                            response = await client.post(ENDPOINT_INGESTADOR, files=files, data=data, timeout=45.0)

                        if response.status_code in [200, 201, 202]:
                            print("[ÉXITO INGESTACIÓN] El stream de bytes fue asimilado correctamente por el backend.")
                            update_expediente_status(expediente_str, str(numero_partida), "PROCESADO", "Descarga e ingestión por stream completada con éxito.")
                        else:
                            raise RuntimeError(f"El ingestador backend rechazó el stream. Código HTTP: {response.status_code}")
                    else:
                        raise RuntimeError("El flujo de descargas devolvió un objeto de bytes vacío o corrupto.")

                    print(f"[ÉXITO] Expediente {expediente_str} finalizado correctamente.")

                except Exception as e:
                    err_msg = f"Fallo en la interfaz de la SUNARP o Ingestador: {str(e)}"
                    print(f"[ERROR CONTENIDO]: {err_msg}")
                    update_expediente_status(expediente_str, str(numero_partida), "ERROR", err_msg)
                    
                    # Intercepción por bloqueo de visualización por partida en el servidor
                    if "cupo_partida_excedido" in err_msg.lower():
                        print(f"\n[SISTEMA CRÍTICO] El DNI activo {active_cred['dni']} fue bloqueado para esta partida por cuota excedida.")
                        print("[SISTEMA] Inhabilitando DNI actual de forma limpia...")
                        
                        force_disable_credential(active_cred["dni"])
                        
                        sesion_activa = False
                        print("[SISTEMA] Cerrando sesión actual por bloqueo de partida. Activando Máquina de Estados para rotar DNI...")
                        break  # Rompe el FOR; el bucle maestro iniciará la re-autenticación
                    
                    # Capturador de caídas de sesión o parpadeos generales
                    if any(keyword in err_msg.lower() for keyword in ["timeout", "not find", "could not", "cupo_agotado", "send_keys", "buscar-partida"]):
                        print("\n[SESIÓN INESTABLE / EXPIRADA]. Activando protocolo de re-autenticación en caliente...")
                        sesion_activa = False
                        break  # Rompe el FOR; la Máquina de Estados re-abrirá una ventana limpia

            # Si el bucle FOR concluye todo el lote sin disparar ningún "break", la tarea terminó
            if sesion_activa:
                lote_completado = True
                print("\n[FINALIZADO] Procesamiento de todos los lotes completado exitosamente de forma inteligente.")

        except Exception as e:
            print(f"\n[ERROR CRÍTICO MAESTRO]: {str(e)}")
            errores_criticos_consecutivos += 1
            await asyncio.sleep(2.0)

        finally:
            if browser is not None:
                browser.stop()
                await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())