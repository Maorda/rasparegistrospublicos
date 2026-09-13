# Ruta: tests/test_data_manager.py
import json
import pytest
from core.data_manager import get_oficina_by_expediente

def test_get_oficina_by_expediente(tmp_path, monkeypatch):
    """Prueba el mapeo dinámico correcto de la oficina registral."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    oficina_file = config_dir / "oficina_registral.json"
    
    data = [{"codigo": "0302", "nombre": "ANDAHUAYLAS"}]
    oficina_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    
    monkeypatch.chdir(tmp_path)
    res = get_oficina_by_expediente("00229-2021-0-0302-JR-CI-01")
    assert res == "ANDAHUAYLAS"

def test_get_oficina_by_expediente_invalid_code(tmp_path, monkeypatch):
    """CORREGIDO: Valida que la función devuelva el código original como fallback

    seguro ante un expediente no mapeado en el JSON de oficinas.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    oficina_file = config_dir / "oficina_registral.json"
    
    data = [{"codigo": "0101", "nombre": "CUSCO"}]
    oficina_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    
    monkeypatch.chdir(tmp_path)
    
    # La función de producción ya no arroja ValueError, devuelve el código como contingencia
    res = get_oficina_by_expediente("00032-2025-0-9999-JR-CI-01")
    assert res == "9999"

def test_check_and_update_expediente_status(tmp_path, monkeypatch):
    """Prueba la persistencia de lectura y escritura sobre el log de expedientes."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    
    from core.data_manager import check_expediente_status, update_expediente_status
    
    assert check_expediente_status("EXP-01") is False
    update_expediente_status("EXP-01", "12345", "PROCESADO", "Éxito")
    assert check_expediente_status("EXP-01") is True
