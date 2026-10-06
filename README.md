# SECA · Consola de revisión para la experta

Interfaz web (Streamlit) para que la experta de SheRoomie revise cada solicitud:

1. **Perfil y expediente**: cómo se fue armando el perfil de la candidata (onboarding, verificación, expediente de solvencia) y las reglas de la casa.
2. **Lectura de variables**: de qué tabla y campo sale cada variable del motor, qué valor tiene en la base, qué valor recibe el motor y si hay algo que revisar (⚠ por revisar, ? desconocida, ✗ inválida, ⊘ excluida por no discriminación).
3. **Cómo decidió el motor**: cada nivel con todas sus reglas (✓ se cumplió, ✗ no se cumplió, ? faltan datos) y los valores reales de la candidata, los ciclos del motor y cómo se publicó cada conclusión.
4. **Veredicto y revisión**: dictamen, condición, acciones, el árbol del porqué y el registro en JSON. La experta indica si está de acuerdo y, si no, el dictamen que daría y el motivo; queda guardado en la tabla `seca_revisiones`.

## Cómo se conecta con el notebook

La interfaz **no tiene una copia del motor**. `motor_notebook.py` abre `MotorInferenciaSBC_SR_v.1.ipynb` y ejecuta sus celdas de código (carga del Excel, auditoría, compilación, validación y motor) hasta antes de los ejemplos de la sección 11. Si cambias el notebook o el Excel, en la barra lateral usa **Origen del motor → Recargar motor**. Si el notebook detiene la carga con un `assert` (por ejemplo, una regla inválida en el Excel), la interfaz muestra ese error.

## Cómo correrla

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre en el navegador (http://localhost:8501). La primera vez crea `sheroomie_demo.db` con 8 solicitudes de ejemplo.

Para usar el notebook y el Excel de la carpeta de Drive del equipo (con Google Drive para escritorio), cambia las rutas en **Origen del motor** o define variables de entorno:

```bash
SECA_NOTEBOOK="G:/Mi unidad/SheRoomie - SBC/MotorInferenciaSBC_SR_v.1.ipynb" \
SECA_EXCEL="G:/Mi unidad/SheRoomie - SBC/SECA_02_Base_Conocimiento_v1.1.xlsx" \
streamlit run app.py
```

## Versión publicada (Streamlit Community Cloud)

La app se despliega desde este repo (rama `main`, archivo `app.py`). Cada `git push` a `main` la actualiza sola.

- **Para cambiar el motor o la base de conocimiento**, sube el notebook o el Excel nuevos al repo con el mismo nombre. En la versión publicada las rutas de **Origen del motor** están fijas porque el motor ejecuta el notebook y nadie con el enlace debe poder elegir qué archivo se ejecuta.
- **Las revisiones no son permanentes.** Se guardan en SQLite y el disco de Streamlit Cloud se borra cuando la app se reinicia, se redespliega o se duerme por inactividad. Si una revisión importa, descarga su registro JSON.
- Cualquiera con el enlace puede abrir la app y guardar revisiones. Los datos son ficticios.

## Los datos

`sheroomie_demo.db` (SQLite) imita las tablas reales de SheRoomie: `users`, `user_preferences`, `properties`, `bookings` y `reports`. Las personas son **ficticias**. Los campos que la app todavía no tiene y que SECA necesita están marcados como **PROPUESTO** en `datos_demo.py`: la tabla `seca_expedientes` (solvencia), `smoking_chip`, `visit_frequency` y las reglas estructuradas de la casa (`smoking_policy`, `predominant_schedule`, `expected_cleanliness`, `visit_tolerance`).

| Solicitud | Caso | Veredicto |
|---|---|---|
| #101 Mariana | Perfil ideal | Aprobada |
| #102 Sofía | Honorarios con referencias parciales, fuma solo afuera, con aval; la solicitud trae otra renta | Aprobada con condición: aval |
| #103 Valeria | Tiene gato y la casa no acepta mascotas | Rechazada para esta habitación |
| #104 Daniela | No capturó su ingreso | Revisión manual + pedir documentos |
| #105 Regina | Renta = 55 % de su ingreso, sin compensación | Rechazada para esta habitación |
| #106 Lucía | Un reporte confirmado | Revisión manual |
| #107 Camila | No respondió si tiene mascota | Revisión manual (falta el dato) |
| #108 Ana Paula | Limpieza degradada por el bug de /profile (`relaxed_clean`) | Revisión manual (dato inválido) |

**Reiniciar datos de ejemplo** (barra lateral) recrea la base y borra las revisiones guardadas.

## Para conectarla a la base real

Solo cambia `adaptador.py`: la tabla `MAPEO` dice de qué tabla y campo sale cada variable. Para Postgres (Neon) basta con reemplazar la conexión SQLite por una de `psycopg` y ajustar las consultas de `leer_expediente`. Hazlo solo con datos anonimizados o con autorización, porque son datos personales.

## Archivos

| Archivo | Qué hace |
|---|---|
| `app.py` | La interfaz |
| `motor_notebook.py` | Carga el motor ejecutando el notebook |
| `adaptador.py` | Traduce la base de datos a hechos del motor (`MAPEO`) y guarda las revisiones |
| `datos_demo.py` | Crea la base de ejemplo |
| `MotorInferenciaSBC_SR_v.1.ipynb`, `SECA_02_Base_Conocimiento_v1.1.xlsx` | Motor y base de conocimiento |
