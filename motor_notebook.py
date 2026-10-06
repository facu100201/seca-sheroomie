"""Carga el motor SECA ejecutando las celdas de MotorInferenciaSBC_SR_v.1.ipynb.

La interfaz NO tiene una copia del motor: lee el notebook y ejecuta sus celdas de código
(carga del Excel, auditoría, compilación, validación y motor) hasta antes de los ejemplos
y pruebas (sección 11 en adelante). Si cambias el notebook o el Excel, basta con
"Recargar motor" en la interfaz.
"""
import contextlib
import io
import json
import linecache
import os
import types
from pathlib import Path

# A partir de esta celda empiezan los ejemplos y las pruebas del notebook: no hacen falta aquí.
CORTE = "CASO_INTEGRADOR"
EXCEL_POR_DEFECTO = "SECA_02_Base_Conocimiento_v1.1.xlsx"

REQUERIDOS = [
    "inferir", "BASE", "REGLAS", "VARIABLES", "CATALOGO", "ESCALAS", "EXCLUIDAS",
    "estado_regla", "validar_hecho", "variables_leidas", "texto_regla", "fmt",
    "explicar", "registrar", "faltantes", "tabla_ciclos", "tabla_cierres",
    "auditoria", "HASH_BC", "VERSION_MOTOR",
]


def _celdas_de_codigo(ruta_notebook):
    nb = json.loads(Path(ruta_notebook).read_text(encoding="utf-8"))
    for celda in nb["cells"]:
        if celda["cell_type"] == "code":
            fuente = celda["source"]
            yield "".join(fuente) if isinstance(fuente, list) else fuente


def cargar_motor(ruta_notebook, ruta_excel):
    ruta_notebook, ruta_excel = Path(ruta_notebook).resolve(), Path(ruta_excel).resolve()
    if not ruta_notebook.exists():
        raise FileNotFoundError(f"No encuentro el notebook: {ruta_notebook}")
    if not ruta_excel.exists():
        raise FileNotFoundError(f"No encuentro el Excel: {ruta_excel}")

    ns = {"__name__": "seca_notebook", "display": lambda *a, **k: None}
    salida, ejecutadas, previo = io.StringIO(), 0, os.getcwd()
    # Fuera de Colab, el bloque 0 lee el Excel desde la carpeta actual: nos movemos a la del Excel.
    os.chdir(ruta_excel.parent)
    try:
        with contextlib.redirect_stdout(salida):
            for i, fuente in enumerate(_celdas_de_codigo(ruta_notebook)):
                if fuente.lstrip().startswith(CORTE):
                    break
                fuente = fuente.replace(EXCEL_POR_DEFECTO, ruta_excel.name)
                nombre = f"<notebook-celda-{i}>"
                linecache.cache[nombre] = (len(fuente), None, fuente.splitlines(True), nombre)
                try:
                    exec(compile(fuente, nombre, "exec"), ns)
                except Exception as e:  # el notebook se detiene con assert si algo no cuadra
                    raise RuntimeError(f"Falló la celda de código #{i + 1} del notebook: {e}") from e
                ejecutadas += 1
    finally:
        os.chdir(previo)

    faltan = [n for n in REQUERIDOS if n not in ns]
    if faltan:
        raise RuntimeError("El notebook no define lo que la interfaz necesita: " + ", ".join(faltan))

    motor = types.SimpleNamespace(**{k: v for k, v in ns.items() if not k.startswith("__")})
    motor.info = {"notebook": str(ruta_notebook), "excel": str(ruta_excel),
                  "celdas_ejecutadas": ejecutadas, "salida": salida.getvalue()}
    return motor
