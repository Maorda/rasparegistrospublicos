# Ruta: flows/query_flow.py
"""Flujo de negocio para configurar y ejecutar los filtros de consulta usando Inyección JS pura y control nativo CDP."""

import asyncio
import random
import nodriver as uc
from core.human_actions import human_click, wait_for_spinner_to_close


async def select_nz_option(page: uc.Tab, item_index: int, search_text: str) -> bool:
    """
    Selecciona una opción en un control nz-select de NG-ZORRO (Angular)
    usando selectores estructurales e interacción segura con el overlay.
    """
    js_inject = f"""
    (() => {{
        const items = document.querySelectorAll('nz-form-item');
        if (!items[{item_index}]) return false;
        
        const control = items[{item_index}].querySelector('nz-select-top-control');
        const input = items[{item_index}].querySelector('input.ant-select-selection-search-input');
        
        if (control) control.click();
        if (input) {{
            input.focus();
            input.value = "{search_text}";
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }}
        return false;
    }})();
    """
    success = await page.evaluate(js_inject)
    if not success:
        return False

    await asyncio.sleep(0.5)

    # Forzamos la selección vía selección directa en el desplegable (CDK Overlay) o por Hardware CDP
    js_click_option = f"""
    (() => {{
        const options = Array.from(document.querySelectorAll('.ant-select-item-option-content'));
        const target = options.find(el => el.textContent.trim().toUpperCase().includes("{search_text.upper()}"));
        if (target) {{
            target.click();
            return true;
        }}
        return false;
    }})();
    """
    option_clicked = await page.evaluate(js_click_option)

    # Si el elemento no estuvo listo en el DOM del Overlay, hacemos fallback al evento CDP
    if not option_clicked:
        await page.send(uc.cdp.input_.dispatch_key_event(type_="keyDown", key="ArrowDown", windows_virtual_key_code=40))
        await asyncio.sleep(0.1)
        await page.send(uc.cdp.input_.dispatch_key_event(type_="keyUp", key="ArrowDown", windows_virtual_key_code=40))
        await asyncio.sleep(0.2)
        await page.send(uc.cdp.input_.dispatch_key_event(type_="keyDown", key="Enter", windows_virtual_key_code=13))
        await asyncio.sleep(0.1)
        await page.send(uc.cdp.input_.dispatch_key_event(type_="keyUp", key="Enter", windows_virtual_key_code=13))

    await page.evaluate("if (document.activeElement) document.activeElement.blur();")
    return True


async def run_query_flow(page: uc.Tab, filter_data: dict) -> None:
    """Configura los dropdowns de la SUNARP y ejecuta la búsqueda de la partida."""
    print(f"[INFO] Preparando filtros para la oficina: '{filter_data['oficina_registral']}'...")

    # 1. SELECCIÓN DE OFICINA REGISTRAL (Primer nz-form-item)
    await select_nz_option(page, item_index=0, search_text=filter_data['oficina_registral'])

    print(f"[INFO] Oficina '{filter_data['oficina_registral']}' fijada. Esperando activación del Área Registral...")
    await asyncio.sleep(random.uniform(1.8, 2.5))

    # 2. SELECCIÓN DE ÁREA REGISTRAL (Segundo nz-form-item)
    print(f"[INFO] Inyectando Área Registral: '{filter_data['area_registral']}'...")
    await select_nz_option(page, item_index=1, search_text=filter_data['area_registral'])

    await asyncio.sleep(1.0)

    # 3. SELECCIÓN DE RADIO BUTTON E INYECCIÓN DE NÚMERO DE PARTIDA
    print(f"[INFO] Inyectando número de partida: {filter_data['numero']}...")
    js_partida_flow = f"""
    (() => {{
        // Clic en Radio "N° de Partida" (nzvalue="2")
        const radio = document.querySelector('label[nzvalue="2"] input') || document.querySelector('label[nzvalue="2"]');
        if (radio) radio.click();

        // Inyección directa en control de formulario Angular
        const numInput = document.querySelector('input[formcontrolname="numero"]');
        if (numInput) {{
            numInput.focus();
            numInput.value = "{str(filter_data['numero']).upper()}";
            numInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            numInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }})();
    """
    await page.evaluate(js_partida_flow)
    await asyncio.sleep(0.8)

    # 4. EJECUCIÓN DE BÚSQUEDA
    btn_buscar = await page.select("button.btn-buscar-partida")
    if btn_buscar:
        # CORREGIDO: Llamada limpia a la firma real de human_click sin pasarle la página
        await human_click(btn_buscar)
        await wait_for_spinner_to_close(page, selector=".ant-spin, .ant-btn-loading", timeout=12.0)
    else:
        raise RuntimeError("No se encontró el botón 'btn-buscar-partida' en el DOM.")
