# Ruta: core/data_manager.py
"""Módulo de utilidades para el mapeo de resoluciones judiciales, logs de control y gestión inteligente de DNI."""

import json
import os
import time
from datetime import datetime, timezone, timedelta


def get_oficina_by_expediente(expediente_str: str) -> str:
    """Extrae el cuarto bloque numérico del expediente (ej. '0302') y busca

    la oficina registral correspondiente en 'config/oficina_registral.json'.
    """
    parts = expediente_str.split("-")
    if len(parts) < 4:
        raise ValueError(f"Formato de expediente inválido: '{expediente_str}'")

    code = parts[3]  # Captura el cuarto bloque numérico (ej: 0302 o 1411)
    file_path = os.path.join("config", "oficina_registral.json")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")
        
    if os.path.getsize(file_path) == 0:
        raise ValueError(f"El archivo {file_path} está vacío. Por favor, rellena la lista de oficinas.")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            oficinas = json.load(f)
    except json.JSONDecodeError as je:
        raise ValueError(f"Error de formato crítico en {file_path}: {str(je)}. Verifica que sea un JSON válido.")

    for item in oficinas:
        if str(item.get("codigo")).zfill(4) == code.zfill(4):
            return item.get("nombre")

    # Retorno seguro por si el código del expediente (como 1411) no está en tu lista actual
    print(f"[AVISO] Código '{code}' no mapeado explícitamente. Se usará el valor original como búsqueda.")
    return code


def check_expediente_status(expediente_str: str) -> bool:
    """Verifica en 'config/control_expedientes.json' si el expediente existe

    y su estado es 'PROCESADO'.
    """
    file_path = os.path.join("config", "control_expedientes.json")

    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    record = records.get(expediente_str)
    if record and record.get("estado") == "PROCESADO":
        return True

    return False


def update_expediente_status(expediente_str: str, partida: str, estado: str, observaciones: str = "") -> None:
    """Registra o actualiza en 'config/control_expedientes.json' los datos del expediente,

    incluyendo su partida, estado, timestamp actual y observaciones.
    """
    file_path = os.path.join("config", "control_expedientes.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    records = {}
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except (json.JSONDecodeError, OSError):
            records = {}

    records[expediente_str] = {
        "partida": partida,
        "estado": estado,
        "observaciones": observaciones,
        "updated_at": datetime.now().isoformat()
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def get_active_credential() -> dict:
    """Obtiene la primera credencial disponible con menos de 5 ingresos en el ciclo diario desde una lista pura JSON.

    Resetea automáticamente los contadores si la fecha_ciclo difiere de la fecha actual de Perú (UTC-5).
    """
    file_path = os.path.join("config", "filtro.json")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de credenciales: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        credentials = json.load(f)

    peru_tz = timezone(timedelta(hours=-5))
    today_str = datetime.now(peru_tz).strftime("%Y-%m-%d")

    changes_made = False

    for cred in credentials:
        if cred.get("fecha_ciclo") != today_str:
            cred["ingresos_ciclo"] = 0
            cred["fecha_ciclo"] = today_str
            cred["timestamp_primer_ingreso"] = 0
            changes_made = True

    if changes_made:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=2, ensure_ascii=False)

    for cred in credentials:
        if int(cred.get("ingresos_ciclo", 0)) < 5:
            return cred

    raise RuntimeError("Todas las credenciales cargadas han agotado sus cupos diarios (5 ingresos).")


def increment_credential_intents(dni: str) -> None:
    """Incrementa en +1 los ingresos_ciclo del DNI especificado dentro de la lista raíz de 'config/filtro.json'."""
    file_path = os.path.join("config", "filtro.json")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de credenciales: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        credentials = json.load(f)

    updated = False
    for cred in credentials:
        if str(cred.get("dni")) == str(dni):
            cred["ingresos_ciclo"] = int(cred.get("ingresos_ciclo", 0)) + 1
            if float(cred.get("timestamp_primer_ingreso", 0)) == 0:
                cred["timestamp_primer_ingreso"] = time.time()
            updated = True
            break

    if updated:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=2, ensure_ascii=False)
