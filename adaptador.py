"""Adaptador base de datos → hechos de SECA.

Cada variable del motor dice de qué tabla y campo sale y cómo se traduce. La tabla `MAPEO`
es conocimiento de integración (no del dominio): la experta la ve tal cual en la pestaña
"Lectura de variables" para comprobar que el dato de la usuaria se leyó bien.
"""
import json
import sqlite3


def _bool(v):
    return None if v is None else bool(v)


def _num(v):
    return None if v is None else (int(v) if float(v).is_integer() else float(v))


def _fuma(ctx):
    # La UI captura si / no / solo_afuera; la BD real solo guarda smoking (bool) y pierde "solo_afuera".
    chip = ctx["pref"]["smoking_chip"]
    if chip is not None:
        return chip, chip, None, None
    bruto = ctx["pref"]["smoking"]
    valor = None if bruto is None else ("si" if bruto else "no")
    return bruto, valor, "Sin chip original: se tradujo smoking (bool) y «solo_afuera» no se puede distinguir (E15)", None


def _renta(ctx):
    precio, de_solicitud = ctx["prop"]["price_monthly"], ctx["book"]["monthly_rent"]
    nota = None
    if de_solicitud is not None and de_solicitud != precio:
        nota = f"La solicitud trae {de_solicitud:,.0f} MXN (lo manda el cliente); se usa la renta de la propiedad (E19)"
    return precio, _num(precio), nota, "Nunca se usa bookings.monthly_rent"


def _campo(tabla, campo, traducir=lambda v: v, info=None):
    # devuelve (valor crudo, valor para el motor, aviso que pide revisión, nota informativa)
    return lambda ctx: (ctx[tabla][campo], traducir(ctx[tabla][campo]), None, info)


# variable SECA, fuente (tabla.campo), cómo se obtiene, estado del campo en la app real, grupo
MAPEO = [
    ("estado_verificacion_identidad", "users.verification_status", _campo("u", "verification_status"), "Implementado", "Candidata"),
    ("metodo_pago_validado", "seca_expedientes.payment_method_validated", _campo("exp", "payment_method_validated", _bool), "Propuesto SECA", "Solvencia"),
    ("ingreso_mensual_comprobable", "seca_expedientes.monthly_income", _campo("exp", "monthly_income", _num), "Propuesto SECA", "Solvencia"),
    ("renta_mensual_referencia", "properties.price_monthly", _renta, "Implementado", "Solvencia"),
    ("tipo_ingreso", "seca_expedientes.income_type", _campo("exp", "income_type"), "Propuesto SECA", "Solvencia"),
    ("antiguedad_laboral_meses", "seca_expedientes.employment_months", _campo("exp", "employment_months", _num), "Propuesto SECA", "Solvencia"),
    ("referencias_verificadas", "seca_expedientes.references_status", _campo("exp", "references_status"), "Propuesto SECA", "Solvencia"),
    ("reportes_confirmados", "COUNT(reports · status = resolved)", lambda ctx: (ctx["n_reportes"], ctx["n_reportes"], None, "Solo cuentan reportes resueltos (E12)"), "Parcial", "Candidata"),
    ("aval_disponible", "seca_expedientes.has_guarantor", _campo("exp", "has_guarantor", _bool), "Propuesto SECA", "Compensaciones"),
    ("acepta_deposito_ampliado", "seca_expedientes.accepts_extra_deposit", _campo("exp", "accepts_extra_deposit", _bool), "Propuesto SECA", "Compensaciones"),
    ("acepta_meses_adelantados", "seca_expedientes.accepts_advance_months", _campo("exp", "accepts_advance_months", _bool), "Propuesto SECA", "Compensaciones"),
    ("horario_actividad", "user_preferences.schedule", _campo("pref", "schedule"), "Implementado", "Hábitos"),
    ("tiene_mascota", "user_preferences.pet_friendly", _campo("pref", "pet_friendly", _bool, "En la candidata pet_friendly significa «tengo mascota» (E14)"), "Implementado", "Hábitos"),
    ("fuma", "user_preferences.smoking_chip · smoking", _fuma, "Parcial", "Hábitos"),
    ("frecuencia_visitas", "user_preferences.visit_frequency", _campo("pref", "visit_frequency"), "Propuesto SECA", "Hábitos"),
    ("nivel_limpieza", "user_preferences.cleanliness_level", _campo("pref", "cleanliness_level"), "Implementado", "Hábitos"),
    ("tiene_hijos", "user_preferences.has_children", _campo("pref", "has_children", _bool), "Implementado", "Hábitos"),
    ("estado_propiedad", "properties.status", _campo("prop", "status"), "Implementado", "Casa"),
    ("casa_acepta_mascotas", "properties.pet_friendly", _campo("prop", "pet_friendly", _bool, "En la casa pet_friendly significa «acepto mascotas» (E14)"), "Implementado", "Casa"),
    ("casa_acepta_fumar", "properties.smoking_policy", _campo("prop", "smoking_policy"), "Propuesto SECA", "Casa"),
    ("casa_horario_predominante", "properties.predominant_schedule", _campo("prop", "predominant_schedule"), "Propuesto SECA", "Casa"),
    ("casa_limpieza_esperada", "properties.expected_cleanliness", _campo("prop", "expected_cleanliness"), "Propuesto SECA", "Casa"),
    ("casa_tolerancia_visitas", "properties.visit_tolerance", _campo("prop", "visit_tolerance"), "Propuesto SECA", "Casa"),
    ("decision_anfitriona", "bookings.decision_host", _campo("book", "decision_host"), "Implementado", "Solicitud"),
]


def _fila(con, sql, *args):
    cur = con.execute(sql, args)
    r = cur.fetchone()
    return None if r is None else dict(zip([d[0] for d in cur.description], r))


def listar_solicitudes(con):
    cur = con.execute("""
        SELECT b.id, u.full_name, p.title, b.created_at
        FROM bookings b JOIN users u ON u.id = b.user_id JOIN properties p ON p.id = b.property_id
        ORDER BY b.id""")
    return [dict(zip(["id", "candidata", "propiedad", "fecha"], r)) for r in cur.fetchall()]


def leer_expediente(con, booking_id, motor):
    book = _fila(con, "SELECT * FROM bookings WHERE id = ?", booking_id)
    ctx = {
        "book": book,
        "u": _fila(con, "SELECT * FROM users WHERE id = ?", book["user_id"]),
        "pref": _fila(con, "SELECT * FROM user_preferences WHERE user_id = ?", book["user_id"]),
        "prop": _fila(con, "SELECT * FROM properties WHERE id = ?", book["property_id"]),
        "exp": _fila(con, "SELECT * FROM seca_expedientes WHERE user_id = ?", book["user_id"]),
        "n_reportes": con.execute("SELECT COUNT(*) FROM reports WHERE reported_user_id = ? AND status = 'resolved'",
                                  (book["user_id"],)).fetchone()[0],
    }
    ctx["prop"]["house_rules"] = json.loads(ctx["prop"]["house_rules"] or "[]")
    ctx["eventos"] = [dict(zip(["fecha", "paso", "detalle"], r)) for r in con.execute(
        "SELECT fecha, paso, detalle FROM onboarding_eventos WHERE user_id = ? ORDER BY fecha", (book["user_id"],))]

    lecturas, hechos = [], {}
    for variable, fuente, obtener, en_app, grupo in MAPEO:
        bruto, valor, aviso, info = obtener(ctx)
        nota = aviso
        ficha = motor.VARIABLES.get(variable, {})
        error = motor.validar_hecho(variable, valor)
        if variable in motor.EXCLUIDAS:
            estado, nota = "⊘ excluida", "Característica protegida: el motor la descarta (no discriminación)"
        elif error:
            estado, nota, valor = "✗ inválida", f"{error}. El motor la trata como desconocida.", None
        elif valor is None:
            estado = "? desconocida"
        elif nota:
            estado = "⚠ revisar"
        else:
            estado = "✓ leída"
        if not error:
            hechos[variable] = valor
        lecturas.append({
            "grupo": grupo, "variable": variable, "ID": ficha.get("id", "—"), "fuente en BD": fuente,
            "valor en BD": "NULL" if bruto is None else str(bruto),
            "valor para el motor": motor.fmt(valor), "tipo": ficha.get("tipo", "—"),
            "estado": estado, "campo en la app": en_app, "nota": " · ".join(x for x in (nota, info) if x),
        })
    return ctx, lecturas, hechos


def guardar_revision(con, booking_id, revisora, de_acuerdo, dictamen_motor, dictamen_final, motivo, registro):
    con.execute("""INSERT INTO seca_revisiones
        (booking_id, fecha, revisora, de_acuerdo, dictamen_motor, dictamen_final, motivo, registro_json)
        VALUES (?, datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?)""",
                (booking_id, revisora, int(de_acuerdo), dictamen_motor, dictamen_final, motivo,
                 json.dumps(registro, ensure_ascii=False, default=str)))
    con.commit()


def revisiones(con, booking_id):
    cur = con.execute("""SELECT fecha, revisora, de_acuerdo, dictamen_motor, dictamen_final, motivo
                         FROM seca_revisiones WHERE booking_id = ? ORDER BY id DESC""", (booking_id,))
    return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
