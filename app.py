"""SECA · Consola de revisión para la experta.

Ejecutar:  streamlit run app.py
El motor se carga desde MotorInferenciaSBC_SR_v.1.ipynb (ver motor_notebook.py).
"""
import json
import os
import re
import sqlite3
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from adaptador import guardar_revision, leer_expediente, listar_solicitudes, revisiones
from datos_demo import asegurar_db, crear_db
from diagnostico import PATRONES, diagnosticar, evidencia_md, interpretacion, leer_excepciones, texto_cadena
from motor_notebook import cargar_motor

AQUI = Path(__file__).parent
NOTEBOOK = os.environ.get("SECA_NOTEBOOK", str(AQUI / "MotorInferenciaSBC_SR_v.1.ipynb"))
EXCEL = os.environ.get("SECA_EXCEL", str(AQUI / "SECA_02_Base_Conocimiento_v1.1.xlsx"))
DB = os.environ.get("SECA_DB", str(AQUI / "sheroomie_demo.db"))
# En la nube (Streamlit Community Cloud monta el repo en /mount/src) las rutas quedan fijas:
# el motor ejecuta el notebook, así que nadie con el enlace debe poder elegir qué archivo se ejecuta.
PUBLICO = os.environ.get("SECA_PUBLICO") == "1" or AQUI.resolve().as_posix().startswith("/mount/src/")

DICTAMEN = {
    "aprobada":                  ("Aprobada", "#2E7D5B", "La candidata puede ocupar la habitación."),
    "aprobada_con_condicion":    ("Aprobada con condición", "#A86A12", "Puede ocuparla si cumple la condición."),
    "revision_manual":           ("Revisión manual", "#3D5A99", "El sistema no debe decidir solo: lo decide una persona."),
    "rechazada_para_habitacion": ("Rechazada para esta habitación", "#B23A48", "No para esta casa; se le sugieren otras."),
}
ESTADO_REGLA = {True: "✓ se cumplió", False: "✗ no se cumplió", None: "? faltan datos"}

st.set_page_config(page_title="SECA · Revisión de expedientes", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 3.4rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .seca-eyebrow {color:#B83A6B; font-weight:600; letter-spacing:.08em; text-transform:uppercase; font-size:.8rem; margin-bottom:.2rem;}
  .seca-card {border:1px solid #E3DFD6; border-radius:12px; padding:1rem 1.2rem; background:#FDFCF9; margin-bottom:.8rem;}
  .seca-card h4 {margin:0 0 .5rem 0;}
  .seca-dato {display:flex; justify-content:space-between; gap:1rem; padding:.18rem 0; border-bottom:1px dashed #ECE8DF; font-size:.92rem;}
  .seca-dato span:first-child {color:#5B6272;}
  .seca-veredicto {border-radius:14px; padding:1.4rem 1.6rem; color:#FBFAF7; margin-bottom:1rem;}
  .seca-veredicto .t {font-size:2rem; font-weight:700; line-height:1.15;}
  .seca-evento {border-left:3px solid #B83A6B; padding:.1rem 0 .7rem .9rem; margin-left:.3rem;}
  .seca-evento small {color:#6B7280;}
  .seca-tabla-wrap {overflow-x:auto; border:1px solid #E3DFD6; border-radius:10px; margin-bottom:.4rem;}
  .seca-tabla {width:100%; border-collapse:collapse; font-size:.88rem;}
  .seca-tabla th {text-align:left; font-weight:600; color:#5B6272; background:#F2EFE8; padding:.45rem .7rem; border-bottom:1px solid #E3DFD6; white-space:nowrap;}
  .seca-tabla td {padding:.45rem .7rem; border-bottom:1px solid #ECE8DF; vertical-align:top;}
  .seca-tabla tr:last-child td {border-bottom:none;}
  .seca-tabla td.ancha {overflow-wrap:anywhere; min-width:16rem; width:55%;}
  .seca-dictamen {margin-bottom:1rem;}
  .seca-dictamen-etiqueta {font-size:.875rem; color:#1E2433; margin-bottom:.35rem;}
  .seca-dictamen-valor {display:inline-block; color:#FBFAF7; font-size:1.45rem; font-weight:600; line-height:1.25; border-radius:10px; padding:.35rem .9rem;}
  .seca-dictamen-valor.oculto {color:#5B6272; background:transparent; border:1px dashed #C9C3B6; font-size:1.2rem;}
  .seca-chip {display:inline-block; border-radius:999px; padding:.2rem .75rem; margin:0 .4rem .4rem 0; font-size:.85rem; font-weight:600; border:1px solid;}
  .seca-chip.si {background:#B83A6B; color:#FBFAF7; border-color:#B83A6B;}
  .seca-chip.no {color:#9AA0AC; border-color:#E3DFD6; background:transparent;}
  .seca-cadena {font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:.85rem; background:#F2EFE8; border-radius:8px; padding:.5rem .75rem; margin-bottom:.4rem; overflow-wrap:anywhere;}
</style>
""", unsafe_allow_html=True)


# ── Motor y base de datos ─────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando el motor desde el notebook…")
def motor_en_cache(notebook, excel, firma):
    return cargar_motor(notebook, excel)


@st.cache_data(show_spinner=False)
def excepciones_en_cache(excel, firma):
    return leer_excepciones(excel)


def firma_archivos(*rutas):
    return tuple(Path(r).stat().st_mtime if Path(r).exists() else 0 for r in rutas)


def conexion():
    asegurar_db(DB)
    return sqlite3.connect(DB, check_same_thread=False)


with st.sidebar:
    st.markdown('<p class="seca-eyebrow">SheRoomie · SECA</p>', unsafe_allow_html=True)
    st.title("Revisión de expedientes")
    with st.expander("Origen del motor", expanded=False):
        notebook = st.text_input("Notebook del motor", NOTEBOOK, disabled=PUBLICO)
        excel = st.text_input("Excel de la base de conocimiento", EXCEL, disabled=PUBLICO)
        if PUBLICO:
            st.caption("En la versión publicada el motor se carga de los archivos del repo; "
                       "para cambiarlo, sube el notebook o el Excel nuevos al repo.")
        if st.button("Recargar motor", width="stretch"):
            st.cache_resource.clear()
        if st.button("Reiniciar datos de ejemplo", width="stretch"):
            crear_db(DB)
            st.toast("Base de ejemplo recreada")

try:
    M = motor_en_cache(notebook, excel, firma_archivos(notebook, excel))
except Exception as e:  # noqa: BLE001
    st.error(f"No pude cargar el motor desde el notebook.\n\n{e}")
    st.stop()

con = conexion()
solicitudes = listar_solicitudes(con)

with st.sidebar:
    st.caption(f"Motor v{M.VERSION_MOTOR} · {len(M.REGLAS)} reglas · base sha256 {M.HASH_BC}")
    st.caption(f"Cargado desde **{Path(M.info['notebook']).name}** ({M.info['celdas_ejecutadas']} celdas) "
               f"y **{Path(M.info['excel']).name}**")
    por_etiqueta = {f"#{s['id']} · {s['candidata']}": s["id"] for s in solicitudes}
    booking_id = por_etiqueta[st.radio("Solicitudes pendientes", list(por_etiqueta))]
    st.caption("Datos de ejemplo: personas ficticias con la forma de las tablas de SheRoomie.")
    predecir = st.toggle("Predecir antes de ver el dictamen",
                         help="Como en el laboratorio de casos: escribe el resultado que esperas antes de ejecutar "
                              "y luego compáralo con lo que concluyó el motor.")

predicciones = st.session_state.setdefault("predicciones", {})
prediccion = predicciones.get(booking_id)
oculto = predecir and prediccion is None

try:
    EXCEPCIONES = excepciones_en_cache(M.info["excel"], firma_archivos(M.info["excel"]))
except Exception as e:  # noqa: BLE001
    EXCEPCIONES = []
    st.warning(f"No pude leer la hoja Excepciones del Excel ({e}). El diagnóstico sale sin preguntas para la experta.")

ctx, lecturas, hechos = leer_expediente(con, booking_id, M)
res = M.inferir(hechos, M.BASE)
H = res["hechos"]
diag = diagnosticar(res, M, EXCEPCIONES)
REGLA_POR_ID = {r["id"]: r for r in M.BASE["reglas"]}
u, pref, prop, exp = ctx["u"], ctx["pref"], ctx["prop"], ctx["exp"]
dictamen = H.get("dictamen")
nombre, color, lectura = DICTAMEN.get(dictamen, ("Sin dictamen", "#5B6272", ""))

st.markdown(f'<p class="seca-eyebrow">Solicitud #{booking_id} · {prop["title"]}</p>', unsafe_allow_html=True)
st.header(u["full_name"])
c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
leidas = sum(l["estado"].startswith(("✓", "⚠")) for l in lecturas if not l["estado"].startswith("⊘"))
total = sum(not l["estado"].startswith("⊘") for l in lecturas)
# Mismo color que el recuadro "Veredicto de SECA"; en modo predicción queda neutro para no dar pistas.
estilo = "seca-dictamen-valor oculto" if oculto else "seca-dictamen-valor"
fondo = "" if oculto else f' style="background:{color}"'
c1.markdown(f'<div class="seca-dictamen"><div class="seca-dictamen-etiqueta">Dictamen del motor</div>'
            f'<span class="{estilo}"{fondo}>{"Oculto hasta tu predicción" if oculto else nombre}</span></div>',
            unsafe_allow_html=True)
c2.metric("Variables leídas", f"{leidas} / {total}")
c3.metric("Reglas disparadas", f"{len(res['disparadas'])} / {len(M.REGLAS)}")
c4.metric("Ciclos del motor", len(res["traza"]["ciclos"]))

tab_perfil, tab_lectura, tab_razon, tab_diagnostico, tab_veredicto = st.tabs(
    ["1 · Perfil y expediente", "2 · Lectura de variables", "3 · Cómo decidió el motor",
     "4 · Diagnóstico del caso", "5 · Veredicto y revisión"])


def tarjeta(titulo, datos):
    filas = "".join(f'<div class="seca-dato"><span>{k}</span><b>{v}</b></div>' for k, v in datos.items())
    st.markdown(f'<div class="seca-card"><h4>{titulo}</h4>{filas}</div>', unsafe_allow_html=True)


def tabla_ajustada(filas, ancha):
    # Los valores salen de la base de datos: se escapan antes de meterlos en HTML.
    columnas = list(filas[0])
    cabecera = "".join(f"<th>{escape(c)}</th>" for c in columnas)
    clase = {c: ' class="ancha"' if c == ancha else "" for c in columnas}
    cuerpo = "".join(
        "<tr>" + "".join(f"<td{clase[c]}>{escape(str(f[c]))}</td>" for c in columnas) + "</tr>"
        for f in filas)
    st.markdown(f'<div class="seca-tabla-wrap"><table class="seca-tabla"><thead><tr>{cabecera}</tr></thead>'
                f"<tbody>{cuerpo}</tbody></table></div>", unsafe_allow_html=True)


def sn(v):
    return "—" if v is None else ("sí" if v else "no")


# ── 1 · Perfil y expediente ───────────────────────────────────────────────────
with tab_perfil:
    st.subheader("Cómo se fue armando el perfil")
    izq, der = st.columns([3, 2])
    with izq:
        a, b = st.columns(2)
        with a:
            tarjeta("Cuenta e identidad", {
                "Identidad (INE + selfie)": u["verification_status"], "Teléfono verificado": sn(u["phone_verified"]),
                "Cuenta activa": sn(u["is_active"]), "Onboarding completo": sn(u["onboarding_completed"]),
                "Reportes confirmados": ctx["n_reportes"]})
            tarjeta("Hábitos declarados (onboarding paso 3)", {
                "Horario": pref["schedule"] or "—", "¿Tiene mascota?": sn(pref["pet_friendly"]),
                "¿Fuma?": pref["smoking_chip"] or f"{sn(pref['smoking'])} (solo bool)",
                "Visitas": pref["visit_frequency"] or "—", "Limpieza": pref["cleanliness_level"] or "—",
                "¿Tiene hijos?": f"{sn(pref['has_children'])} · no se usa"})
        with b:
            tarjeta("Expediente de solvencia", {
                "Ingreso mensual": "—" if exp["monthly_income"] is None else f"{exp['monthly_income']:,.0f} MXN",
                "Tipo de ingreso": exp["income_type"] or "—", "Antigüedad": f"{exp['employment_months']} meses",
                "Referencias": exp["references_status"] or "—", "Pago validado": sn(exp["payment_method_validated"]),
                "Aval": sn(exp["has_guarantor"]), "Acepta depósito ampliado": sn(exp["accepts_extra_deposit"]),
                "Acepta meses adelantados": sn(exp["accepts_advance_months"])})
            tarjeta(f"Casa · {prop['city']}", {
                "Renta": f"{prop['price_monthly']:,.0f} MXN", "Acepta mascotas": sn(prop["pet_friendly"]),
                "Fumar": prop["smoking_policy"], "Horario predominante": prop["predominant_schedule"],
                "Limpieza esperada": prop["expected_cleanliness"], "Tolerancia a visitas": prop["visit_tolerance"]})
            st.caption("Reglas en texto libre: " + " · ".join(prop["house_rules"]))
    with der:
        st.markdown("**Historial del expediente**")
        for e in ctx["eventos"]:
            fecha = e["fecha"].replace("T", " ")[:16]
            st.markdown(f'<div class="seca-evento"><b>{e["paso"]}</b><br>{e["detalle"]}<br><small>{fecha}</small></div>',
                        unsafe_allow_html=True)

# ── 2 · Lectura de variables ──────────────────────────────────────────────────
with tab_lectura:
    st.subheader("Cómo leyó el motor cada dato de la base de datos")
    st.caption("Cada fila es una variable del Diccionario: de qué campo sale, qué valor tiene en la base y "
               "qué valor recibe el motor. Revisa sobre todo las marcadas con ⚠, ? y ✗.")
    df = pd.DataFrame(lecturas)
    conteo = df["estado"].str[0].value_counts()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("✓ leídas", conteo.get("✓", 0))
    k2.metric("⚠ por revisar", conteo.get("⚠", 0))
    k3.metric("? desconocidas", conteo.get("?", 0))
    k4.metric("✗ inválidas", conteo.get("✗", 0))
    k5.metric("⊘ excluidas", conteo.get("⊘", 0))
    solo_alertas = st.toggle("Mostrar solo las que hay que revisar")
    vista = df[~df["estado"].str[0].isin(["✓"])] if solo_alertas else df
    st.dataframe(vista[["estado", "ID", "variable", "valor en BD", "valor para el motor", "fuente en BD",
                        "grupo", "tipo", "campo en la app", "nota"]],
                 column_config={"nota": st.column_config.TextColumn(width="large")},
                 hide_index=True, width="stretch", height=min(38 * (len(vista) + 1), 900))
    st.markdown("**Valores que calcula el motor (nivel 0)**")
    st.dataframe(pd.DataFrame([{"variable": d["variable"], "cálculo": d["funcion"],
                                "a partir de": ", ".join(f"{a} = {M.fmt(H.get(a))}" for a in d["argumentos"]),
                                "resultado": M.fmt(d["valor"])} for d in res["traza"]["derivaciones"]]),
                 hide_index=True, width="stretch")
    if res["traza"]["descartados"]:
        st.info("Descartadas antes de razonar (no discriminación): " + ", ".join(res["traza"]["descartados"]))

# ── 3 · Cómo decidió el motor ─────────────────────────────────────────────────
def formulario_prediccion():
    st.subheader("Antes de ver cómo decidió el motor")
    st.caption("Como en el laboratorio de casos: con los hechos de las pestañas 1 y 2, escribe qué esperas que "
               "concluya SECA. Después la pestaña 4 compara tu predicción con lo que observó el motor.")
    with st.form(f"prediccion_{booking_id}"):
        esperado = st.selectbox("Dictamen que esperas", list(DICTAMEN), format_func=lambda k: DICTAMEN[k][0])
        patrones = st.multiselect("Patrón que esperas", list(PATRONES),
                                  format_func=lambda k: f"{PATRONES[k][0]} · {PATRONES[k][1]}")
        reglas_txt = st.text_input("Reglas que crees que decidirán el dictamen", placeholder="R06, R25")
        motivo = st.text_area("Por qué lo esperas")
        if st.form_submit_button("Registrar predicción y ver el dictamen", type="primary"):
            ids = [f"R{int(n):02d}{s.lower()}" for n, s in re.findall(r"[rR](\d+)([a-zA-Z]?)", reglas_txt)]
            predicciones[booking_id] = {"dictamen": esperado, "patrones": patrones,
                                        "reglas": sorted(set(ids)), "motivo": motivo.strip()}
            st.rerun()


with tab_razon:
    if oculto:
        formulario_prediccion()
    else:
        st.subheader("Cómo decidió el motor")
        st.caption("El motor razona por niveles. En cada uno revisa qué reglas se cumplen con los datos, "
                   "las dispara y al final junta sus conclusiones según la política de cada salida.")
        disparadas = set(res["disparadas"])
        for nivel in M.BASE["niveles"]:
            reglas = M.BASE["reglas_por_nivel"][nivel]
            n_disp = sum(r["id"] in disparadas for r in reglas)
            cierra = ", ".join(M.BASE["variables_por_nivel"][nivel])
            with st.expander(f"Nivel {nivel} · {n_disp} de {len(reglas)} reglas disparadas · concluye: {cierra}",
                             expanded=(n_disp > 0)):
                filas = [{"regla": r["id"],
                          "resultado": ESTADO_REGLA[M.estado_regla(r, H)] + (" → disparada" if r["id"] in disparadas else ""),
                          "regla con los valores de la candidata": M.texto_regla(r, H),
                          "origen": r["origen"], "validación": r["estado"]} for r in reglas]
                orden = {"✓": 0, "?": 1, "✗": 2}
                filas.sort(key=lambda f: orden[f["resultado"][0]])
                # tabla HTML y no st.dataframe: st.dataframe corta el texto largo de la regla en una sola línea
                tabla_ajustada(filas, ancha="regla con los valores de la candidata")
        st.markdown("**Ciclos del motor** (conjunto conflicto y regla elegida en cada vuelta)")
        st.dataframe(M.tabla_ciclos(res), hide_index=True, width="stretch")
        st.markdown("**Cómo se publicó cada conclusión**")
        st.caption("combinado = juntó lo que dijeron las reglas · cierre = ninguna regla lo contradijo · "
                   "respaldo = faltaban datos para decidir")
        st.dataframe(M.tabla_cierres(res), hide_index=True, width="stretch")

# ── 4 · Diagnóstico del caso ──────────────────────────────────────────────────
EXCEPCION_COLUMNAS = {"ID": "ID", "Regla(s) relacionada(s)": "reglas", "Excepción / conflicto": "excepción / conflicto",
                      "Pregunta para el experto": "pregunta para la experta", "Estado": "estado"}


def tabla_excepciones(excepciones, vacio):
    if excepciones:
        tabla_ajustada([{v: e[k] for k, v in EXCEPCION_COLUMNAS.items()} for e in excepciones],
                       ancha="pregunta para la experta")
    else:
        st.warning(vacio)


def comparar(prediccion):
    observadas = [r["id"] for r in diag["decisivas"]]
    previstas = prediccion["reglas"]
    acierto = lambda ok: "✓ coincide" if ok else "✗ no coincide"
    detalle = " · ".join(x for x in [
        f"acertaste {', '.join(r for r in previstas if r in observadas)}" if set(previstas) & set(observadas) else "",
        f"no previste {', '.join(r for r in observadas if r not in previstas)}" if set(observadas) - set(previstas) else "",
        f"no decidieron {', '.join(r for r in previstas if r not in observadas)}" if set(previstas) - set(observadas) else "",
    ] if x)
    nombre_patrones = lambda ps: ", ".join(PATRONES[p][0] for p in ps) or "—"
    return [
        {"qué": "Dictamen", "esperado": DICTAMEN[prediccion["dictamen"]][0], "observado": nombre,
         "resultado": acierto(prediccion["dictamen"] == dictamen)},
        {"qué": "Patrón", "esperado": nombre_patrones(prediccion["patrones"]),
         "observado": nombre_patrones(diag["tipos"]), "resultado": acierto(set(prediccion["patrones"]) == set(diag["tipos"]))},
        {"qué": "Reglas que deciden", "esperado": ", ".join(previstas) or "—",
         "observado": ", ".join(observadas) or "ninguna (respaldo)",
         "resultado": acierto(set(previstas) == set(observadas)) + (f" · {detalle}" if detalle else "")},
    ]


with tab_diagnostico:
    if oculto:
        st.info("Registra primero tu predicción en la pestaña 3.")
    else:
        st.subheader("Diagnóstico del caso")
        st.caption("Metodología del laboratorio de casos (Sesión 7): no basta con que el motor funcione; "
                   "hay que ver cómo se comporta el conocimiento. Un caso puede tener varios patrones a la vez.")
        st.markdown("".join(f'<span class="seca-chip {"si" if p in diag["tipos"] else "no"}" title="{v[1]}">{v[0]}</span>'
                            for p, v in PATRONES.items()), unsafe_allow_html=True)
        st.markdown("\n".join(f"- {f}" for f in interpretacion(diag, res, M)))

        st.markdown("#### Resultado esperado y resultado observado")
        if prediccion:
            tabla_ajustada(comparar(prediccion), ancha="resultado")
            if prediccion["motivo"]:
                st.caption(f"Tu razonamiento: {prediccion['motivo']}")
            if st.button("Borrar mi predicción"):
                predicciones.pop(booking_id)
                st.rerun()
        else:
            st.caption("No registraste una predicción para esta solicitud. Activa «Predecir antes de ver el "
                       "dictamen» en la barra lateral para escribirla antes de ver el resultado.")

        st.markdown("#### ¿Dos reglas concluyen valores distintos? (conflicto)")
        if not diag["conflictos"]:
            st.success("Sin conflictos: ninguna variable recibió valores incompatibles de reglas que se cumplieron.")
        for c in diag["conflictos"]:
            propuestas = " · ".join(f"{', '.join(rids)} propone **{M.fmt(v)}**" for v, rids in c["propuestas"].items())
            st.markdown(f"**`{c['variable']}`**: {propuestas} → el motor publicó **{M.fmt(c['publicado'])}**")
            if c["resuelto"]:
                st.caption(f"Lo resolvió la política «{c['politica']}» ({c['politica_texto']}): {c['por_que']} "
                           "Resolver un conflicto es conocimiento de control: la política está en el notebook, "
                           "no en el Excel, y tiene que validarla la experta.")
            else:
                st.caption("La política «único» no admite dos valores: el conflicto queda sin resolver y se "
                           "publica el respaldo.")
            tabla_excepciones(c["excepciones"], "Ninguna excepción del Excel cubre este conflicto: hay que registrarla "
                                                "en la hoja Excepciones con su pregunta para la experta.")

        st.markdown("#### ¿Una conclusión alimenta otra regla? (encadenamiento)")
        if diag["cadenas"]:
            st.caption("Cada cadena va de los hechos que lee la primera regla hasta el dictamen. «cierre» significa "
                       "que ninguna regla concluyó esa variable y todas pudieron evaluarse (mundo cerrado).")
            for cadena in diag["cadenas"]:
                st.markdown(f'<div class="seca-cadena">{escape(texto_cadena(cadena, res, M))}</div>',
                            unsafe_allow_html=True)
        else:
            via = res["traza"]["cierres"].get("dictamen", {}).get("via", "—")
            st.info(f"El dictamen no sale de ninguna regla (vía: {via}). Se publicó porque no hubo datos "
                    "suficientes para que una regla de dictamen se cumpliera.")

        st.markdown("#### ¿Falta un hecho necesario? (ambigüedad)")
        amb = diag["ambiguedad"]
        if not amb["faltan"]:
            st.success("No falta ningún dato que necesite una regla. La decisión de la anfitriona llega después "
                       "del dictamen y no cuenta como faltante (E03).")
        else:
            st.markdown(f"Falta **{', '.join(amb['faltan'])}**. Desconocido no significa no: las reglas que lo leen "
                        "no se tratan como falsas.")
            tabla_ajustada([{"regla": rid, "estado": ESTADO_REGLA[M.estado_regla(REGLA_POR_ID[rid], H)],
                             "regla con los valores de la candidata": M.texto_regla(REGLA_POR_ID[rid], H)}
                            for rid in amb["directas"]], ancha="regla con los valores de la candidata")
            if amb["respaldos"]:
                st.caption("Se publicaron por respaldo: " + " · ".join(
                    f"{r['variable']} = {M.fmt(r['valor'])}" for r in amb["respaldos"]))
            tabla_excepciones(amb["excepciones"], "Ninguna excepción del Excel cubre este dato faltante: hay que "
                                                  "registrarla con su pregunta para la experta.")

        st.markdown("#### ¿Las reglas que decidieron están validadas?")
        if diag["decisivas"]:
            pendientes = [r for r in diag["decisivas"] if r["estado"].lower() != "validado"]
            tabla_ajustada([{"regla": r["id"], "regla con los valores de la candidata": M.texto_regla(r, H),
                             "origen": r["origen"], "validación": r["estado"]} for r in diag["decisivas"]],
                           ancha="regla con los valores de la candidata")
            if pendientes:
                st.warning(f"{len(pendientes)} de {len(diag['decisivas'])} reglas que decidieron este dictamen no "
                           "están validadas. Que el motor funcione no demuestra que la regla sea correcta.")
        else:
            st.caption("Ninguna regla sostiene el dictamen: salió por respaldo.")

        st.download_button("Descargar evidencia del caso (Markdown)",
                           evidencia_md(f"Solicitud #{booking_id} · {u['full_name']}", res, M, diag, prediccion,
                                        {k: v[0] for k, v in DICTAMEN.items()}),
                           file_name=f"evidencia_solicitud_{booking_id}.md", mime="text/markdown")
        st.caption("La evidencia sigue los 7 puntos de la actividad: descripción, hechos iniciales, reglas "
                   "involucradas, resultado esperado, resultado observado, interpretación y pregunta de validación.")

# ── 5 · Veredicto y revisión ──────────────────────────────────────────────────
with tab_veredicto:
    if oculto:
        st.info("Registra primero tu predicción en la pestaña 3.")
    else:
        izq, der = st.columns([3, 2])
        with izq:
            condicion = H.get("condicion_aplicada")
            extra = f" · condición: {condicion}" if condicion not in (None, "ninguna") else ""
            st.markdown(f'<div class="seca-veredicto" style="background:{color}"><div style="opacity:.85">Veredicto de SECA</div>'
                        f'<div class="t">{nombre}{extra}</div><div style="margin-top:.4rem">{lectura}</div></div>',
                        unsafe_allow_html=True)
            r1, r2, r3 = st.columns(3)
            r1.metric("Solvencia", M.fmt(H.get("nivel_solvencia")))
            r2.metric("Compatibilidad", M.fmt(H.get("nivel_compatibilidad")))
            r3.metric("Restricción dura", M.fmt(H.get("restriccion_dura_violada")))
            falt = [f for f in M.faltantes(res) if f != "decision_anfitriona"]
            if falt:
                st.warning("Datos que faltaron para decidir: " + ", ".join(falt))
            if H.get("estado_solicitud_resultante") is None:
                st.caption("La decisión de la anfitriona sigue pendiente: SECA recomienda y ella decide (E03).")
            st.markdown("**Acciones que recomienda**")
            st.markdown("\n".join(f"- {a.replace('_', ' ')}" for a in sorted(H.get("acciones") or [])))
            st.markdown("**Por qué** — árbol de reglas, con los valores reales y el origen de cada regla")
            st.code("\n".join(M.explicar(res, "dictamen")), language=None)
            registro = M.registrar(res)
            registro["diagnostico"] = {
                "patrones": diag["tipos"],
                "conflictos": [{"variable": c["variable"], "propuestas": {M.fmt(v): r for v, r in c["propuestas"].items()},
                                "publicado": c["publicado"], "politica": c["politica"],
                                "excepciones": [e["ID"] for e in c["excepciones"]]} for c in diag["conflictos"]],
                "faltan": diag["ambiguedad"]["faltan"],
                "reglas_decisivas": [r["id"] for r in diag["decisivas"]],
            }
            registro["prediccion"] = prediccion
            st.download_button("Descargar registro del dictamen (JSON)",
                               json.dumps(registro, ensure_ascii=False, indent=2, default=str),
                               file_name=f"dictamen_solicitud_{booking_id}.json", mime="application/json")
        with der:
            st.markdown("#### Revisión de la experta")
            st.caption("Tu revisión queda guardada junto con el registro del motor. Si no estás de acuerdo, "
                       "deja el motivo: así sabemos qué regla corregir en la v2.")
            with st.form(f"revision_{booking_id}", clear_on_submit=True):
                revisora = st.text_input("Revisora")
                acuerdo = st.radio("¿Estás de acuerdo con el veredicto?", ["Sí", "No"], horizontal=True)
                nombres = {v[0]: k for k, v in DICTAMEN.items()}
                final = nombres[st.selectbox("Dictamen final", list(nombres),
                                             index=list(DICTAMEN).index(dictamen) if dictamen in DICTAMEN else 2)]
                motivo = st.text_area("Motivo / qué regla cambiarías")
                if st.form_submit_button("Guardar revisión", type="primary", width="stretch"):
                    de_acuerdo = acuerdo == "Sí" and final == dictamen
                    if not revisora.strip():
                        st.error("Escribe el nombre de la revisora.")
                    elif not de_acuerdo and not motivo.strip():
                        st.error("Si cambias el dictamen, explica el motivo.")
                    else:
                        registro["override_humano"] = None if de_acuerdo else {
                            "revisora": revisora, "dictamen_final": final, "motivo": motivo}
                        guardar_revision(con, booking_id, revisora, de_acuerdo, dictamen, final, motivo, registro)
                        st.success("Revisión guardada.")
            historial = revisiones(con, booking_id)
            if historial:
                st.markdown("**Revisiones anteriores**")
                st.dataframe(pd.DataFrame(historial).assign(
                    de_acuerdo=lambda d: d["de_acuerdo"].map({1: "sí", 0: "no"})),
                    hide_index=True, width="stretch")
