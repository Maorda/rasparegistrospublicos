# Ruta: tests/test_data_manager.py
"""Pruebas unitarias TDD para el core de administración de expedientes y datos de entrada."""

import json
import pytest
from core.data_manager import (
    get_oficina_by_expediente,
    check_expediente_status,
    update_expediente_status,
)


def test_get_oficina_by_expediente(tmp_path, monkeypatch):
    """Prueba que el parseo del código de expediente retorne el nombre correcto de oficina."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    oficina_file = config_dir / "oficina_registral.json"

    data = [
        {"codigo": "0101", "nombre": "CUSCO"},
        {"codigo": "0302", "nombre": "ANDAHUAYLAS"}
    ]
    oficina_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    expediente = "00229-2021-0-0302-JR-CI-01"
    oficina = get_oficina_by_expediente(expediente)
    assert oficina == "ANDAHUAYLAS"


def test_get_oficina_by_expediente_invalid_code(tmp_path, monkeypatch):
    """Prueba la captura controlada de errores cuando el código no existe en la base de datos."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    oficina_file = config_dir / "oficina_registral.json"

    data = [{"codigo": "0101", "nombre": "CUSCO"}]
    oficina_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="No se encontró oficina registral"):
        get_oficina_by_expediente("00229-2021-0-9999-JR-CI-01")


def test_check_and_update_expediente_status(tmp_path, monkeypatch):
    """Prueba el ciclo completo de lectura, escritura y actualización de estados del log JSON."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    monkeypatch.chdir(tmp_path)

    expediente = "00229-2021-0-0302-JR-CI-01"

    # Verificación inicial en archivo inexistente
    assert check_expediente_status(expediente) is False

    # Actualizar a ERROR
    update_expediente_status(expediente, partida="12345678", estado="ERROR", observaciones="Falló captcha")
    assert check_expediente_status(expediente) is False

    # Actualizar a PROCESADO
    update_expediente_status(expediente, partida="12345678", estado="PROCESADO", observaciones="Éxito")
    assert check_expediente_status(expediente) is True

    # Verificar estructura interna del JSON resultante guardado en disco
    control_file = config_dir / "control_expedientes.json"
    content = json.loads(control_file.read_text(encoding="utf-8"))
    assert expediente in content
    assert content[expediente]["partida"] == "12345678"
    assert content[expediente]["estado"] == "PROCESADO"
    assert content[expediente]["observaciones"] == "Éxito"
    assert "updated_at" in content[expediente]
