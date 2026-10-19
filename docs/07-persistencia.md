# 7. Persistencia y acceso a la base de datos

## Conexión

`app/database/session.py` administra un único motor (`Engine`) global por proceso:

```python
configure(url=None)  # crea el motor: create_engine(url, pool_pre_ping=True)
get_engine()  # devuelve el motor; lo crea con la URL de .env si no existe
session_scope()  # context manager transaccional
```

| Aspecto | Detalle |
|---------|---------|
| **URL** | `get_settings().database_url`. Es `DATABASE_URL` si está definida; si no, se arma como `postgresql+psycopg://POSTGRES_USER:POSTGRES_PASSWORD@POSTGRES_HOST:POSTGRES_PORT/POSTGRES_DB`. |
| **Driver** | psycopg 3 (binario). |
| **Pool** | Pool por defecto de SQLAlchemy (`QueuePool`, 5 conexiones + 10 de *overflow*). Con `pool_pre_ping=True` se descartan conexiones caídas, por ejemplo tras reiniciar el contenedor. |
| **Alcance** | Un motor por proceso de Streamlit, compartido por todas las sesiones de navegador. |
| **Pruebas** | Llaman a `configure("sqlite://")` con `StaticPool` para tener una BD en memoria por prueba. |

## Transacciones: `session_scope()`

```python
@contextmanager
def session_scope():
    session = _session_factory()  # sessionmaker(expire_on_commit=False)
    try:
        yield session
        session.commit()  # commit al salir sin errores
    except CommitBeforeRaiseError:
        session.commit()  # errores que deben conservar lo hecho (ver abajo)
        raise
    except Exception:
        session.rollback()  # rollback ante cualquier otra excepción
        raise
    finally:
        session.close()
```

Cada bloque `with session_scope() as s:` es **una transacción**. Hay dos detalles importantes:

- **`expire_on_commit=False`.**
  - Los objetos cargados siguen siendo legibles después del commit y del `close()`. Por eso la
    UI puede usar el `User` devuelto por `current_user()` durante todo el rerun.
  - En cambio, las **relaciones perezosas** (*lazy loading*) **no** funcionan fuera de la
    sesión: lanzan `DetachedInstanceError`.
  - Por eso los servicios cargan por adelantado las relaciones que la vista necesita, con
    `selectinload`. Por ejemplo, `list_subjects` carga `Subject.items`, `get_post` carga el
    autor, los comentarios con su autor y los "me gusta", y `list_challenges` carga los
    creador (los conteos de participantes se calculan en SQL).
- **Objetos desacoplados.** Para modificar un objeto que vino de otra sesión, como el usuario
  actual, las vistas usan `s.merge(user)` dentro de la nueva transacción.
- **Errores que conservan cambios (`CommitBeforeRaiseError`).** Algunos errores de dominio deben
  guardar lo que ya se hizo antes de lanzarse. El caso es `accounts.InvalidCodeError`: un código
  incorrecto suma un intento fallido; si la transacción se revirtiera, el límite de 5 intentos
  nunca se aplicaría. Esas excepciones heredan de `CommitBeforeRaiseError` y `session_scope` hace
  commit antes de relanzarlas.
- **Columna diferida.** `User.avatar` es `deferred`: no se carga con el usuario. Leerla fuera de
  la sesión fallaría, por eso la UI usa `users.avatar_bytes(session, user_id)`.

## Patrones de lectura y escritura en la UI

### Lectura

Las vistas abren una sesión y dibujan **dentro** del bloque, así pueden recorrer relaciones ya
cargadas:

```python
with session_scope() as s:
    subjects = academics.list_subjects(s, user.id)
    summary = academics.summarize(subjects, user.current_semester)
    st.metric("Promedio general", formatting.fmt_grade(summary.general_average))
    ...
```

### Escritura: `actions.run_action`

```python
def run_action(fn, success=None, rerun=True):
    try:
        with session_scope() as s:
            result = fn(s)  # el servicio valida y escribe
    except USER_ERRORS as exc:  # AuthError, AcademicError, ChallengeError, …
        st.error(str(exc))  # la transacción ya hizo rollback
        return None
    except IntegrityError:  # doble clic: la restricción única ya impidió el duplicado
        flash("Esa acción ya se había realizado.", "ℹ️")
        st.rerun()
    if success:
        flash(success)  # toast tras el rerun
    if rerun:
        st.rerun()
    return result
```

- Cada acción usa una **transacción propia**, independiente de la sesión de lectura que la
  rodea.
- Un doble clic rápido (seguir, dar "me gusta", unirse a un reto, bloquear) puede intentar
  insertar dos veces la misma fila. La clave primaria o la restricción única lo impide, y
  `run_action` convierte el `IntegrityError` en un aviso en lugar de mostrar la traza.
- `st.rerun()` se llama **después** del commit. Streamlit implementa `st.rerun()` lanzando una
  excepción, y si se lanzara dentro de una sesión con cambios pendientes, provocaría un
  rollback.

## Qué se almacena y dónde

| Dato | Ubicación | Formato |
|------|-----------|---------|
| Credenciales (con Keycloak) | BD `keycloak` | Hash con la política de contraseñas por defecto de Keycloak. Nunca en texto plano. |
| Credenciales (modo local) | `users.password_hash` | bcrypt (`$2b$…`). |
| Perfil | `users` | Columnas de texto. Correo en minúsculas. |
| Foto de perfil | `users.avatar` (`bytea`, columna diferida) | PNG de 256×256 generado con Pillow: se recorta al centro en cuadrado, se redimensiona y se convierte a RGBA. La imagen original **no** se guarda. Límite de subida: 5 MB. En la UI se muestra como `data:image/png;base64,…`, en caché (`st.cache_data`) por usuario y `avatar_updated_at`. |
| Avatar por defecto | (no se guarda) | SVG con las iniciales, generado al vuelo. El color sale del hash MD5 del username. |
| Plan de estudios | `users` (`program`, `study_plan`, `current_semester`, `total_semesters`) + `subjects` | |
| Pensum del catálogo | Código: `app/database/seeds/pensums.py` | Al "cargar pensum" se copian las materias a `subjects` como `pendiente`. |
| Notas | `grade_items.grade` (float), `weight` (float o NULL) | Escala configurable. |
| Promedios, créditos y ranking | **No se guardan** | Se calculan en cada consulta a partir de las tablas base (ver [reglas](10-reglas-de-negocio.md)). El puntaje del ranking se calcula en SQL (`ROW_NUMBER` por reto para el bono). |
| Etiquetas del foro | `posts.tags` | Texto separado por comas, en minúsculas. |
| Reglas de retos | Código: `app/services/challenge_rules.py` | `challenges.rule` guarda sólo el código (`first_post`, …). |
| Estado de sesión de la UI | Memoria del servidor (`st.session_state`) | No persiste. Las sesiones con contraseña vencen a las `SESSION_TTL_HOURS` horas (12 por defecto). |
| Códigos de verificación por correo | `verification_codes.code_hash` | `HMAC-SHA256` con `APP_SECRET_KEY` (en desarrollo, si está vacía, el secreto del cliente de Keycloak). Caducan a los 15 min. |
| Secreto TOTP del 2FA | BD `keycloak` | Lo guarda y valida Keycloak. La app nunca lo ve. |
| Bloqueos y reportes | `user_blocks`, `user_reports` | |
| Eliminación programada | `users.deletion_requested_at`, `deletion_scheduled_for` | La purga borra sus retos de la comunidad, y la fila y su contenido en cascada. Los retos globales se conservan. |
| Correos enviados | No se guardan | En desarrollo se ven en Mailpit (http://localhost:8025). |

## Consultas destacadas

| Necesidad | Técnica |
|-----------|---------|
| Conteo de comentarios y "me gusta" por publicación | Subconsultas escalares correlacionadas en `forum.list_posts`, que permiten ordenar por ellas. |
| Visibilidad de retos | `or_(kind == global, visibility == publico, creator_id == yo, creator_id IN (subconsulta de a quién sigo))`. Los admins ven todos (`true()`). |
| Retos de quienes sigo y "sólo de personas que sigo" en el foro | `IN (SELECT followed_id FROM follows WHERE follower_id = :yo)`. |
| Métricas del panel | `count(*)` con filtros y `GROUP BY` por usuario; se combinan en un `DataFrame` de pandas. |
| Actividad diaria | Fechas de los últimos *N* días, agrupadas por día con pandas (`value_counts`). |
| Búsquedas | `lower(col) LIKE '%texto%'` sobre varias columnas. |
| Desempate en logins | Usuario o correo comparados con `func.lower`. |

## Creación del esquema

`python -m app.database.init_db` (lo ejecuta `make up` o `make init-db`):

1. `Base.metadata.create_all(engine)`: crea las tablas, índices y restricciones que **no
   existan**. No modifica las tablas existentes.
1. `SCHEMA_UPGRADES` y `CHECK_UPGRADES`: sólo en PostgreSQL, sentencias idempotentes que
   actualizan tablas existentes sin perder datos: columnas nuevas (`ADD COLUMN IF NOT EXISTS`),
   el cambio de `challenges.creator_id` a `ON DELETE SET NULL` y las restricciones `CHECK`
   agregadas después (se crean sólo si no existen en `pg_constraint`).
1. Índices: recorre los índices declarados en los modelos y crea los que falten
   (`Index.create(checkfirst=True)`), también en tablas que ya existían.
2. `seed_base()` (`app/database/seeds/base.py`):
   - Crea o actualiza el usuario `APP_ADMIN_USERNAME` con rol `admin`, más el hash local si
     `AUTH_PROVIDER=local`.
   - Inserta los retos globales que falten, identificados por su `rule`.

Opciones:

- `--reset`: ejecuta `drop_all` antes de `create_all` (**borra todos los datos** de la app).
- `--demo`: carga los datos de demostración.

## Evolución del esquema

El proyecto **no usa una herramienta de migraciones**:

- **Tablas nuevas:** las crea `create_all`.
- **Columnas nuevas en tablas existentes:** se agregan a la lista `SCHEMA_UPGRADES` de
  `app/database/init_db.py` y se aplican con `make init-db` (o `make up`). Así se agregaron las columnas
  de activación y de eliminación de cuentas.
- **Índices nuevos:** basta con declararlos en el modelo; `init_db` los crea si faltan.
- **Restricciones `CHECK` nuevas:** se declaran en el modelo y se agregan a `CHECK_UPGRADES`.
- **Cambios de tipo, renombres o borrados de columnas:** requieren `make reset-db`. Así se agregó,
  en su momento, `subjects.category`.

Para conservar los datos en entornos reales se recomienda incorporar **Alembic**:

```bash
.venv/bin/pip install alembic
.venv/bin/alembic init migrations
# en migrations/env.py: target_metadata = app.database.models.Base.metadata
.venv/bin/alembic revision --autogenerate -m "baseline"
.venv/bin/alembic upgrade head
```

## Ejemplos de consultas SQL útiles

```sql
-- Promedio simple de ítems por materia de un estudiante
SELECT s.semester, s.name, s.status, round(avg(g.grade)::numeric, 2) AS nota
FROM subjects s JOIN users u ON u.id = s.user_id
LEFT JOIN grade_items g ON g.subject_id = s.id
WHERE u.username = 'laura.gomez'
GROUP BY s.id ORDER BY s.semester, s.name;

-- Créditos aprobados por categoría
SELECT u.username, s.category, sum(s.credits) AS creditos
FROM subjects s JOIN users u ON u.id = s.user_id
WHERE s.status = 'aprobada'
GROUP BY u.username, s.category ORDER BY u.username;

-- Orden de llegada en un reto
SELECT c.title, u.username, p.completed_at
FROM challenge_participants p
JOIN challenges c ON c.id = p.challenge_id JOIN users u ON u.id = p.user_id
WHERE p.completed_at IS NOT NULL
ORDER BY c.id, p.completed_at;
```

> La primera consulta usa promedio simple. La app usa promedio ponderado cuando todos los ítems
> tienen porcentaje.
