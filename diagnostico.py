"""Diagnóstico del caso con la metodología del laboratorio de la Sesión 7 (SIAST).

El profesor clasifica cada caso en cuatro patrones estructurales:
- normal: las conclusiones pueden coexistir;
- encadenado: una regla necesita un hecho que produjo otra (A → R1 → B → R2 → C);
- conflictivo: dos reglas aplicables concluyen valores distintos para la misma variable;
- ambiguo: falta un hecho necesario (desconocido no significa no).

Aquí se calculan a partir de la traza que devuelve `inferir()`; no se toca el motor. A cada
conflicto o ambigüedad se le ligan las excepciones de la hoja "Excepciones" del Excel cuyas
reglas relacionadas lo cubren, con su pregunta para la experta.
"""
import re

import pandas as pd

# La decisión de la anfitriona llega después del dictamen: que falte no es ambigüedad del caso (E03).
PENDIENTES_POR_DISENO = {"decision_anfitriona"}
SIN_RIVALES = {"suma", "conjunto"}   # en estas políticas varios aportes se acumulan, no compiten


def leer_excepciones(ruta_excel):
    df = pd.read_excel(ruta_excel, sheet_name="Excepciones", header=3, dtype=str)
    return df.dropna(subset=["ID"]).fillna("").apply(lambda col: col.str.strip()).to_dict("records")


def _ids_de(texto, todas):
    # "R24–R31", "R04 / R05", "V07 / R06–R09". Se compara por número: el Excel dice R04 y el motor
    # lo compiló como R04a y R04b; R24–R31 incluye cualquier sufijo dentro del rango.
    numero = lambda rid: int(re.match(r"R(\d+)", rid).group(1))
    ids = set()
    for a, b in re.findall(r"R(\d+)[a-z]?\s*[–-]\s*R(\d+)", texto):
        ids |= {r for r in todas if int(a) <= numero(r) <= int(b)}
    for n, sufijo in re.findall(r"R(\d+)([a-z]?)", texto):
        ids |= {r for r in todas if numero(r) == int(n) and (not sufijo or r.endswith(sufijo))}
    return ids


def excepciones_de(reglas, excepciones, todas):
    return [e for e in excepciones if set(reglas) & _ids_de(e["Regla(s) relacionada(s)"], todas)]


def soporte(motor, cierre, valor):
    if cierre["via"] != "combinado":
        return []
    regla = motor.SOPORTE.get(cierre["politica"], motor.POR_DEFECTO_SOPORTE)
    return regla(cierre["aportes"], valor)


def conflictos(res, motor):
    # Misma variable, valores distintos de reglas que sí se dispararon.
    salida = []
    for variable, c in res["traza"]["cierres"].items():
        propuestas = {}
        for valor, rid in c["aportes"]:
            propuestas.setdefault(valor, []).append(rid)
        if c["politica"] in SIN_RIVALES or len(propuestas) < 2:
            continue
        ganador = res["hechos"].get(variable)
        salida.append({
            "variable": variable, "propuestas": propuestas, "publicado": ganador, "via": c["via"],
            "politica": c["politica"], "politica_texto": motor.POLITICA_TEXTO[c["politica"]],
            "resuelto": not c["conflicto"],
            "por_que": motor.BASE["politicas"][variable].get("por_que", ""),
            "reglas": sorted({rid for _, rid in c["aportes"]}),
        })
    return salida


def cadenas(res, motor, variable="dictamen"):
    """Caminos hecho → regla → conclusión intermedia → regla → … que terminan en `variable`.

    Un eslabón A → v → B existe solo si B lee la variable v y A sostiene el valor publicado de v:
    es la dependencia que pide el laboratorio ("¿la segunda podría ejecutarse sin la primera?").
    Si v se publicó por cierre de mundo cerrado (ninguna regla la concluyó y todas pudieron
    evaluarse), el eslabón es ("cierre", v). Cada camino es una lista de pares (regla, variable).
    """
    reglas = {r["id"]: r for r in motor.BASE["reglas"]}
    cierres, hechos = res["traza"]["cierres"], res["hechos"]

    def sostienen(v):
        c = cierres.get(v)
        if c is None or v in res["entradas"]:
            return []
        return soporte(motor, c, hechos.get(v)) or (["cierre"] if c["via"] == "cierre" else [])

    def caminos(rid, v):
        if rid == "cierre":
            return [[("cierre", v)]]
        previos = [(w, p) for w in sorted(motor.variables_leidas(reglas[rid])) for p in sostienen(w)]
        if not previos:
            return [[(rid, v)]]
        return [camino + [(rid, v)] for w, p in previos for camino in caminos(p, w)]

    todos = [c for rid in sostienen(variable) if rid != "cierre" for c in caminos(rid, variable)]
    return sorted(todos, key=lambda c: (-len(c), c))


def ambiguedad(res, motor):
    hechos = res["hechos"]
    faltan = [f for f in motor.faltantes(res) if f not in PENDIENTES_POR_DISENO]
    if not faltan:
        return {"faltan": [], "indeterminadas": [], "respaldos": [], "directas": []}
    # Reglas que no pudieron evaluarse por algo que falta, sin contar lo que llega después del dictamen.
    indeterminadas = [r["id"] for r in motor.BASE["reglas"]
                      if motor.estado_regla(r, hechos) is None
                      and any(hechos.get(v) is None for v in motor.variables_leidas(r) - PENDIENTES_POR_DISENO)]
    respaldos = [{"variable": v, "valor": hechos.get(v), "indeterminadas": c["indeterminadas"]}
                 for v, c in res["traza"]["cierres"].items()
                 if c["via"] == "respaldo" and set(c["indeterminadas"]) & set(indeterminadas)]
    # Las que leen el dato faltante (o un valor calculado a partir de él), se hayan podido evaluar o no:
    # ahí está la pregunta para la experta; las de más abajo solo heredan la incertidumbre.
    derivadas = motor.BASE["derivadas"]
    toca = lambda v: v in faltan or any(a in faltan for a in derivadas.get(v, (None, ()))[1])
    directas = [r["id"] for r in motor.BASE["reglas"] if any(toca(v) for v in motor.variables_leidas(r))]
    return {"faltan": faltan, "indeterminadas": indeterminadas, "respaldos": respaldos, "directas": directas}


def reglas_decisivas(res, motor, variable="dictamen", vistos=None):
    # Reglas que sostienen el valor publicado de `variable` y, hacia atrás, las que sostienen lo que leen.
    vistos = vistos if vistos is not None else set()
    c = res["traza"]["cierres"].get(variable)
    if c is None or variable in vistos:
        return []
    vistos.add(variable)
    reglas = {r["id"]: r for r in motor.BASE["reglas"]}
    salida = []
    for rid in soporte(motor, c, res["hechos"].get(variable)):
        if rid not in salida:
            salida.append(rid)
        for v in sorted(motor.variables_leidas(reglas[rid])):
            salida += [x for x in reglas_decisivas(res, motor, v, vistos) if x not in salida]
    return salida


def diagnosticar(res, motor, excepciones):
    todas = [r["id"] for r in motor.BASE["reglas"]]
    conf, amb = conflictos(res, motor), ambiguedad(res, motor)
    for c in conf:
        c["excepciones"] = excepciones_de(c["reglas"], excepciones, todas)
    amb["excepciones"] = excepciones_de(amb["directas"], excepciones, todas)
    cad = cadenas(res, motor)
    # Los patrones no se excluyen: el caso 2 del laboratorio es normal y encadenado a la vez.
    tipos = [t for t, hay in [("normal", not conf and not amb["faltan"]),
                              ("encadenado", any(sum(r != "cierre" for r, _ in c) >= 2 for c in cad)),
                              ("conflictivo", conf), ("ambiguo", amb["faltan"])] if hay]
    reglas = {r["id"]: r for r in motor.BASE["reglas"]}
    return {"tipos": tipos, "conflictos": conf, "cadenas": cad, "ambiguedad": amb,
            "decisivas": [reglas[r] for r in reglas_decisivas(res, motor)]}


# ── Textos: cadenas, interpretación y evidencia en el formato de la actividad ──
PATRONES = {
    "normal":      ("Normal", "las conclusiones pueden coexistir sin contradicción"),
    "encadenado":  ("Encadenado", "una regla necesita un hecho que produjo otra"),
    "conflictivo": ("Conflictivo", "dos reglas aplicables concluyen valores distintos para la misma variable"),
    "ambiguo":     ("Ambiguo", "falta un hecho necesario: desconocido no significa no"),
}


def texto_cadena(cadena, res, motor):
    h = res["hechos"]
    reglas = {r["id"]: r for r in motor.BASE["reglas"]}
    # Arranca con los hechos de entrada (o calculados) que lee la primera regla: A → R1 → B → R2 → C.
    primera = cadena[0][0]
    leidos = [] if primera == "cierre" else [
        f"{v} = {motor.fmt(h.get(v))}" for v in sorted(motor.variables_leidas(reglas[primera]))
        if v in res["entradas"] or v in motor.BASE["derivadas"]]
    pasos = [f"[{', '.join(leidos)}]"] if leidos else []
    for regla, variable in cadena:
        pasos.append(f"{'cierre' if regla == 'cierre' else regla} ⟶ {variable} = {motor.fmt(h.get(variable))}")
    return " ⟶ ".join(pasos)


def interpretacion(d, res, motor):
    h, frases = res["hechos"], []
    if "normal" in d["tipos"]:
        frases.append("Caso normal: ninguna variable recibió valores incompatibles y no faltó ningún dato necesario.")
    for c in d["conflictos"]:
        propuestas = "; ".join(f"{', '.join(rids)} propone {motor.fmt(v)}" for v, rids in c["propuestas"].items())
        if c["resuelto"]:
            frases.append(f"Conflicto en {c['variable']}: {propuestas}. El motor publicó {motor.fmt(c['publicado'])} "
                          f"con la política «{c['politica']}» ({c['politica_texto']}). Esa política es conocimiento "
                          f"de control: hay que validarla con la experta, no basta con que el código funcione.")
        else:
            frases.append(f"Conflicto sin resolver en {c['variable']}: {propuestas}. La política «único» no admite "
                          f"dos valores, así que el motor publicó el respaldo ({motor.fmt(c['publicado'])}).")
    if "encadenado" in d["tipos"]:
        larga = d["cadenas"][0]
        n = sum(r != "cierre" for r, _ in larga)
        frases.append(f"Encadenado: el dictamen depende de conclusiones intermedias; la cadena más larga "
                      f"tiene {n} reglas ({' → '.join(r for r, _ in larga if r != 'cierre')}).")
    a = d["ambiguedad"]
    if a["faltan"]:
        publicados = ", ".join(f"{r['variable']} = {motor.fmt(r['valor'])}" for r in a["respaldos"])
        frases.append(f"Ambiguo: falta {', '.join(a['faltan'])}. Las reglas que lo leen ({', '.join(a['directas'])}) "
                      f"no se tratan como falsas; lo que dependía de ellas se publicó por respaldo ({publicados}).")
    return frases


def evidencia_md(caso, res, motor, d, prediccion, nombres_dictamen):
    h = res["hechos"]
    nombre = lambda v: nombres_dictamen.get(v, motor.fmt(v))
    involucradas = sorted({r["id"] for r in d["decisivas"]} | {x for c in d["conflictos"] for x in c["reglas"]}
                          | set(d["ambiguedad"]["directas"]))
    reglas = {r["id"]: r for r in motor.BASE["reglas"]}
    lineas = [f"# Evidencia del caso · {caso}", "",
              f"Motor SECA v{motor.VERSION_MOTOR} · base sha256 {motor.HASH_BC}", "",
              "## 1. Descripción", f"Patrón: {', '.join(PATRONES[t][0] for t in d['tipos'])}.", "",
              "## 2. Hechos iniciales"]
    lineas += [f"- {k} = {motor.fmt(v)}" for k, v in sorted(res["entradas"].items())]
    lineas += ["", "## 3. Reglas involucradas"]
    lineas += [f"- {rid} [{reglas[rid]['origen']} · {reglas[rid]['estado']}]: {motor.texto_regla(reglas[rid], h)}"
               for rid in involucradas]
    lineas += ["", "## 4. Resultado esperado"]
    if prediccion:
        lineas += [f"- Dictamen: {nombre(prediccion['dictamen'])}",
                   f"- Patrón: {', '.join(PATRONES[t][0] for t in prediccion['patrones']) or '—'}",
                   f"- Reglas: {', '.join(prediccion['reglas']) or '—'}",
                   f"- Por qué: {prediccion['motivo'] or '—'}"]
    else:
        lineas.append("No se registró una predicción antes de ver el dictamen.")
    lineas += ["", "## 5. Resultado observado",
               f"- Dictamen: {nombre(h.get('dictamen'))}",
               f"- Condición: {motor.fmt(h.get('condicion_aplicada'))}",
               f"- Reglas que lo decidieron: {', '.join(r['id'] for r in d['decisivas']) or 'ninguna (respaldo)'}",
               "", "## 6. Interpretación"]
    lineas += [f"- {f}" for f in interpretacion(d, res, motor)]
    lineas += ["", "## 7. Conflicto / excepción y pregunta de validación"]
    ligadas = {e["ID"]: e for c in d["conflictos"] for e in c["excepciones"]}
    ligadas.update({e["ID"]: e for e in d["ambiguedad"]["excepciones"]})
    if ligadas:
        lineas += [f"- **{e['ID']}** ({e['Estado'] or 'sin estado'}): {e['Excepción / conflicto']} "
                   f"Pregunta: {e['Pregunta para el experto']}" for e in ligadas.values()]
    elif d["conflictos"] or d["ambiguedad"]["faltan"]:
        lineas.append("Ninguna excepción del Excel cubre esta situación: hay que registrarla.")
    else:
        lineas.append("No aplica: sin conflictos ni datos faltantes.")
    return "\n".join(lineas) + "\n"
