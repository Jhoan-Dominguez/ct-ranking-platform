# 12. Desarrollo, calidad y pruebas

## Flujo de trabajo

```bash
make create          # una sola vez
make up              # servicios
make run             # la app; Streamlit recarga al guardar archivos ("Rerun" o "Always rerun")
make test            # pruebas rápidas, sin Docker
make lint            # antes de hacer commit (el hook también lo hace automáticamente)
```

## Calidad de código

### Herramientas

| Herramienta | Configuración | Qué hace |
|-------------|---------------|----------|
| **isort** | `[tool.isort]` en `pyproject.toml`: `profile = "black"`, `line_length = 100`, `known_first_party = ["app"]` | Ordena los imports en tres grupos: estándar, terceros y `app`. |
| **ruff check** | `[tool.ruff.lint]`: reglas `E, F, W, B, UP, SIM, C4, N, RUF` | Linter: errores, estilo, bugbear, pyupgrade, simplificaciones, comprehensions, nombres. `RUF001-003` se ignoran porque el contenido está en español (tildes y signos). |
| **ruff format** | `[tool.ruff.format]`: comillas dobles, 100 columnas | Formateador compatible con black. |
| **pre-commit-hooks** | `.pre-commit-config.yaml` | Espacios finales, salto de línea final, validación de YAML, JSON y TOML, archivos grandes y marcas de conflicto. |

### pre-commit

`make create` instala el hook. En cada `git commit` se ejecutan, sobre los archivos en
*staging*, los hooks en este orden: higiene → isort → `ruff check --fix` → `ruff format`. Si
alguno modifica archivos, el commit se aborta para revisar los cambios y volver a agregarlos.

```bash
make lint                                    # todos los archivos versionados
.venv/bin/pre-commit run --files app/x.py    # archivos concretos (incluso sin versionar)
make format                                  # isort + ruff fix + ruff format en app/ tests/ scripts/
```

> `pre-commit run --all-files` sólo revisa los archivos **versionados** en Git.

## Pruebas automáticas

- **Ubicación y ejecución:** las pruebas están en `tests/` y usan pytest
  (`[tool.pytest.ini_options]` en `pyproject.toml`).
- **Entorno de prueba** (`tests/conftest.py`):
  - Fuerza `AUTH_PROVIDER=local` y `MAIL_BACKEND=memory`: los correos quedan en
    `mailer.OUTBOX`, y las pruebas leen de ahí los códigos.
  - Cada prueba recibe una BD **SQLite en memoria** nueva: `configure("sqlite://")` +
    `StaticPool` + `create_all`.
  - La fixture `make_user` crea usuarios con `auth.register`.
- **Alcance:** las pruebas cubren la **capa de servicios**. No necesitan Docker ni Keycloak.

```bash
make test                                                     # todas
.venv/bin/python -m pytest tests/test_challenges.py           # un archivo
.venv/bin/python -m pytest tests/test_academics.py::test_credit_progress_by_category_counts_retakes_once
.venv/bin/python -m pytest -k pensum -v                       # por nombre
```

| Archivo | Cubre |
|---------|-------|
| `test_academics.py` | Nota simple, ponderada y mixta; materia sin ítems; promedios ponderados por créditos y estados; CRUD de ítems con validación de escala y del 100 %; propiedad; **avance de créditos por categoría con materias repetidas**; **carga idempotente del pensum**; validación de categoría. |
| `test_challenges.py` | Sólo un admin crea retos globales; orden del ranking y bonus del primero; visibilidad "sólo seguidores"; retos cerrados; reglas automáticas; un usuario antiguo completa al unirse. |
| `test_auth.py` | Registro y login local (usuario o correo); reglas y cambio de contraseña; cuenta deshabilitada; dominio institucional y exención de administradores; login con Google (creación y vínculo de usuario, rechazo de otros dominios, de correos no verificados y de cuentas deshabilitadas); regresión del primer login desde Keycloak. |
| `test_users.py` | Alias único y límites de semestre del perfil. |
| `test_social.py` | Seguir, dejar de seguir y mensajes de apoyo no leídos. |
| `test_forum.py` | Flujo del foro y permisos (autor o admin). |
| `test_admin.py` | Marca de estudiante en riesgo y métricas globales. |
| `test_accounts.py` | Eliminación con contraseña y código por correo; código de un solo uso, límite de intentos y expiración; cancelación y purga con borrado en cascada; ocultamiento de cuentas en eliminación. |
| `test_moderation.py` | Bloqueos (seguimientos, mensajes, búsqueda, foro, bidireccionalidad) y reportes (validaciones, duplicados, cierre por admin, conservación al borrar el contenido). |

### Pruebas de la interfaz (manuales o con `AppTest`)

Streamlit incluye `streamlit.testing.v1.AppTest` para ejecutar páginas sin navegador. Ejemplo
para renderizar una vista como un usuario concreto (requiere la BD levantada):

```python
from streamlit.testing.v1 import AppTest


def view_script(module_name, root):
    import importlib, sys

    sys.path.insert(0, root)
    importlib.import_module(f"app.ui.pages.{module_name}").render()


at = AppTest.from_function(view_script, args=("academics", "/ruta/al/proyecto"))
at.session_state["user_id"] = 3
at.run()
assert not at.exception
print([e.label for e in at.expander])
```

### Pruebas en un navegador real (JavaScript)

`AppTest` no ejecuta JavaScript ni permite hacer clic en un `st.expander`. Para lo que depende
del navegador (el menú lateral que se expande con el mouse, `app/ui/assets/sidebar_hover.js`, o abrir un
expander a mano) se usa **Selenium con Firefox en modo headless**, instalado en un entorno
virtual aparte para no agregarlo a las dependencias del proyecto:

```bash
python3 -m venv /tmp/selenv && /tmp/selenv/bin/pip install selenium
make run   # en otra terminal
```

```python
from selenium import webdriver

opts = webdriver.FirefoxOptions()
opts.add_argument("-headless")
# Firefox headless dice que no hay mouse; esto simula un puntero fino con hover,
# necesario para que sidebar_hover.js se active.
opts.set_preference("ui.primaryPointerCapabilities", 6)
opts.set_preference("ui.allPointerCapabilities", 6)
driver = webdriver.Firefox(options=opts)
driver.get("http://localhost:8501")
# … iniciar sesión, ocultar el menú y mover el puntero con ActionBuilder.move_to_location(5, 400)
# … verificar section[data-testid="stSidebar"] → data-collapsed == "false"
```

### Pruebas de extremo a extremo con correo (Keycloak + Mailpit)

Los flujos que pasan por el correo (activación, configuración del 2FA, código de eliminación) se
probaron con Selenium contra los servicios reales:

- **Leer los correos.** Mailpit expone una API: `GET http://localhost:8025/api/v1/messages` y
  `GET /api/v1/message/{ID}`. Con ella se extraen los enlaces (`…/login-actions/action-token?key=…`)
  y los códigos.
- **Configurar el 2FA.** En la página de Keycloak, «Unable to scan?» muestra la clave del QR.
  Con ella se calcula el código TOTP (RFC 6238: HMAC-SHA1, 30 s, 6 dígitos) con `hmac` de la
  biblioteca estándar.
- **Evitar el bloqueo por fuerza bruta.** Los intentos fallidos muy seguidos activan la
  protección y bloquean la cuenta por un rato. Hay que dejar unos segundos entre intentos y, con
  2FA, esperar a la siguiente ventana de 30 s antes de reutilizar un código.

## Convenciones del código

- **Idioma:** la interfaz, los mensajes, los comentarios y la documentación están en español.
  Los identificadores del código están en inglés.
- **Servicios:**
  - `session` es el primer argumento y los opcionales son *keyword-only* (`*`).
  - Nunca hacen `commit` ni llaman a Streamlit.
  - Los errores para el usuario se lanzan como `XxxError(ValueError)` con un mensaje claro.
  - Las relaciones que la vista necesita se cargan con `selectinload`.
- **Vistas:**
  - Las lecturas se hacen dentro de `with session_scope() as s:`.
  - Las escrituras pasan siempre por `actions.run_action(lambda s: …, "mensaje")`.
  - Para modificar el usuario actual se usa `s.merge(user)`.
  - Dentro de un bucle, las lambdas capturan las variables por argumento por defecto
    (`lambda s, iid=item.id: …`).
- **Widgets:** cuando se repiten en una lista, usar `key` únicas con el id del objeto
  (`f"del_i_{item.id}"`).

## Cómo extender la plataforma

### Agregar una página

1. Crear `app/ui/pages/nueva.py` con una función `render()` que empiece con
   `user = session.require_user()` (`from app.ui.components import session`).
2. Registrarla en `app/main.py`, dentro del grupo correspondiente:
   `st.Page(nueva.render, title="…", icon="…", url_path="…")`.

### Agregar un campo a una tabla

1. Agregar el `mapped_column` en `app/database/models.py`, con `default=`.
2. Actualizar el servicio (validación) y la vista.
3. Recrear el esquema (`make reset-db`) o crear una migración, si ya se incorporó Alembic.
4. Documentarlo en [Modelo de datos](06-modelo-de-datos.md).

### Agregar una regla de reto automático

1. Agregar una entrada en `_rules()` de `app/services/challenge_rules.py`:
   `"codigo": Rule("Descripción", meta, lambda s, u: medida, "unidad")`.
2. Para que sea un reto global por defecto, agregarlo a `GLOBAL_CHALLENGES` en
   `app/database/seeds/base.py` y ejecutar `make init-db`, que inserta los retos que falten.
3. También se puede crear desde la UI como admin: *Crear reto → Reto global → Verificación
   automática*.

### Agregar un nuevo tipo de error de dominio

Agregar la clase a la tupla `USER_ERRORS` de `app/ui/components/actions.py`. Así `run_action` la muestra como
mensaje en lugar de dejar que Streamlit muestre la traza del error.

### Agregar un programa al catálogo de pensum

Ver [Datos iniciales](11-datos-iniciales-y-demo.md#agregar-otro-programa-al-catálogo).
