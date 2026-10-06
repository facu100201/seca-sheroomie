"""Base de datos SQLite de ejemplo con la forma de las tablas de SheRoomie.

Todas las personas son ficticias. Las tablas `users`, `user_preferences`, `properties`,
`bookings` y `reports` siguen los nombres del esquema real (Drizzle). Los campos marcados
"PROPUESTO" no existen todavía en la app: son los que SECA necesita capturar.
"""
import json
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY, full_name TEXT, email TEXT,
    verification_status TEXT, phone_verified INTEGER, is_active INTEGER,
    onboarding_completed INTEGER, created_at TEXT
);
CREATE TABLE user_preferences (
    user_id INTEGER PRIMARY KEY, city TEXT, budget_min TEXT, budget_max TEXT,
    schedule TEXT, pet_friendly INTEGER, smoking INTEGER,
    smoking_chip TEXT,          -- PROPUESTO: hoy la UI captura si/no/solo_afuera pero la BD guarda bool
    visit_frequency TEXT,       -- PROPUESTO: no existe en la app
    cleanliness_level TEXT, noise_level TEXT, has_children INTEGER, updated_at TEXT
);
CREATE TABLE properties (
    id INTEGER PRIMARY KEY, title TEXT, city TEXT, status TEXT,
    price_monthly REAL, deposit REAL, pet_friendly INTEGER, house_rules TEXT,
    smoking_policy TEXT,        -- PROPUESTO: hoy es texto libre en house_rules
    predominant_schedule TEXT,  -- PROPUESTO
    expected_cleanliness TEXT,  -- PROPUESTO
    visit_tolerance TEXT        -- PROPUESTO
);
CREATE TABLE bookings (
    id INTEGER PRIMARY KEY, user_id INTEGER, property_id INTEGER, status TEXT,
    monthly_rent REAL, decision_host TEXT, created_at TEXT
);
CREATE TABLE reports (
    id INTEGER PRIMARY KEY, reported_user_id INTEGER, reason TEXT, status TEXT, created_at TEXT
);
CREATE TABLE seca_expedientes (   -- PROPUESTO: datos de solvencia que la app aún no captura
    user_id INTEGER PRIMARY KEY, payment_method_validated INTEGER, monthly_income REAL,
    income_type TEXT, employment_months INTEGER, references_status TEXT,
    has_guarantor INTEGER, accepts_extra_deposit INTEGER, accepts_advance_months INTEGER,
    captured_at TEXT
);
CREATE TABLE onboarding_eventos (
    id INTEGER PRIMARY KEY, user_id INTEGER, fecha TEXT, paso TEXT, detalle TEXT
);
CREATE TABLE seca_revisiones (
    id INTEGER PRIMARY KEY, booking_id INTEGER, fecha TEXT, revisora TEXT,
    de_acuerdo INTEGER, dictamen_motor TEXT, dictamen_final TEXT, motivo TEXT, registro_json TEXT
);
"""

PROPIEDADES = [
    # id, título, ciudad, status, renta, depósito, acepta mascotas, reglas texto, fumar, horario, limpieza, visitas
    (1, "Casa Coyoacán · habitación 2", "Ciudad de México", "published", 7500, 7500, 0,
     ["No fumar", "No mascotas", "Silencio después de las 11pm"], "no", "early_bird", "ordenada", "ocasional"),
    (2, "Depa Roma Norte · habitación A", "Ciudad de México", "published", 12000, 12000, 1,
     ["Mascotas pequeñas bienvenidas", "Fumar solo en el balcón", "Limpieza semanal rotativa"],
     "solo_afuera", "flexible", "muy_ordenada", "frecuente"),
    (3, "Casa Providencia · habitación 3", "Guadalajara", "published", 16500, 16500, 0,
     ["No fumar", "No mascotas", "No visitas de más de 2 noches"], "no", "night_owl", "relajada", "ocasional"),
]

BASE_CANDIDATA = dict(
    verification_status="verified", phone_verified=1, is_active=1, onboarding_completed=1,
    schedule="early_bird", pet_friendly=0, smoking=0, smoking_chip="no", visit_frequency="ocasional",
    cleanliness_level="ordenada", noise_level="moderate", has_children=0,
    payment_method_validated=1, monthly_income=30000, income_type="nomina", employment_months=18,
    references_status="si", has_guarantor=0, accepts_extra_deposit=0, accepts_advance_months=0,
    reportes_resueltos=0, propiedad=1, monthly_rent=None, decision_host=None,
)

CANDIDATAS = [
    ("Mariana Ortega (demo)", "Perfil ideal", {}),
    ("Sofía Ramírez (demo)", "Honorarios, referencias parciales, fuma solo afuera, con aval",
     dict(income_type="honorarios", references_status="parcial", smoking_chip="solo_afuera",
          has_guarantor=1, monthly_rent=6500)),
    ("Valeria Núñez (demo)", "Tiene gato; la casa no acepta mascotas", dict(pet_friendly=1, has_children=1)),
    ("Daniela Cruz (demo)", "No capturó su ingreso", dict(monthly_income=None)),
    ("Regina Flores (demo)", "Renta = 55 % de su ingreso, sin compensación",
     dict(propiedad=3, schedule="night_owl", cleanliness_level="relajada")),
    ("Lucía Herrera (demo)", "Un reporte confirmado en la plataforma",
     dict(propiedad=2, pet_friendly=1, schedule="flexible", cleanliness_level="muy_ordenada",
          visit_frequency="frecuente", reportes_resueltos=1)),
    ("Camila Torres (demo)", "No respondió si tiene mascota", dict(pet_friendly=None)),
    ("Ana Paula Gómez (demo)", "Su limpieza se degradó al editar /profile (bug E16)",
     dict(propiedad=2, pet_friendly=1, schedule="flexible", smoking_chip=None,
          cleanliness_level="relaxed_clean", visit_frequency="frecuente")),
]


def crear_db(ruta):
    ruta = Path(ruta)
    ruta.unlink(missing_ok=True)
    con = sqlite3.connect(ruta)
    con.executescript(ESQUEMA)
    for p in PROPIEDADES:
        con.execute("INSERT INTO properties VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*p[:7], json.dumps(p[7], ensure_ascii=False), *p[8:]))
    titulos = {p[0]: p[1] for p in PROPIEDADES}
    for uid, (nombre, _, cambios) in enumerate(CANDIDATAS, start=1):
        c = {**BASE_CANDIDATA, **cambios}
        dia = f"2026-09-{uid + 10:02d}"
        con.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
                    (uid, nombre, f"candidata{uid}@demo.sheroomie.mx", c["verification_status"],
                     c["phone_verified"], c["is_active"], c["onboarding_completed"], f"{dia}T10:00:00"))
        con.execute("INSERT INTO user_preferences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uid, "Ciudad de México", "6000", "15000", c["schedule"], c["pet_friendly"],
                     c["smoking"], c["smoking_chip"], c["visit_frequency"], c["cleanliness_level"],
                     c["noise_level"], c["has_children"], f"{dia}T10:12:00"))
        con.execute("INSERT INTO seca_expedientes VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (uid, c["payment_method_validated"], c["monthly_income"], c["income_type"],
                     c["employment_months"], c["references_status"], c["has_guarantor"],
                     c["accepts_extra_deposit"], c["accepts_advance_months"], f"{dia}T18:30:00"))
        precio = next(p[4] for p in PROPIEDADES if p[0] == c["propiedad"])
        con.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?)",
                    (100 + uid, uid, c["propiedad"], "pending", c["monthly_rent"] or precio,
                     c["decision_host"], f"{dia}T19:05:00"))
        for _ in range(c["reportes_resueltos"]):
            con.execute("INSERT INTO reports (reported_user_id, reason, status, created_at) VALUES (?,?,?,?)",
                        (uid, "harassment", "resolved", "2026-08-02T12:00:00"))
        eventos = [
            ("10:00", "Cuenta creada", "Registro con Clerk; se crea la fila en users"),
            ("10:05", "Onboarding · paso 2", "Ciudad y presupuesto (6,000 – 15,000 MXN)"),
            ("10:12", "Onboarding · paso 3", "Hábitos: horario, mascota, fuma, limpieza, hijos"),
            ("10:20", "Teléfono verificado", "OTP de Twilio Verify"),
            ("10:31", "Identidad enviada", "INE frente y reverso + selfie"),
            ("16:02", "Identidad revisada", f"Resultado: {c['verification_status']}"),
            ("18:30", "Expediente de solvencia", "Ingreso, tipo de ingreso, antigüedad, referencias y compensaciones"),
            ("19:05", "Solicitud enviada", f"A «{titulos[c['propiedad']]}»"),
        ]
        for hora, paso, detalle in eventos:
            con.execute("INSERT INTO onboarding_eventos (user_id, fecha, paso, detalle) VALUES (?,?,?,?)",
                        (uid, f"{dia}T{hora}:00", paso, detalle))
    con.commit()
    con.close()
    return ruta


def asegurar_db(ruta):
    ruta = Path(ruta)
    return ruta if ruta.exists() else crear_db(ruta)


def descripcion_casos():
    return {f"candidata{i}": d for i, (_, d, _) in enumerate(CANDIDATAS, start=1)}


if __name__ == "__main__":
    print("Base creada en", crear_db(Path(__file__).with_name("sheroomie_demo.db")))
