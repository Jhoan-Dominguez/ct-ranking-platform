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
  - Fuerza `AUTH_PROVIDER=local`.
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
| `test_social_forum_auth.py` | Registro y login local (usuario o correo); reglas y cambio de contraseña; cuenta deshabilitada; alias único y límites de semestre; seguir y mensajes no leídos; flujo y permisos del foro; marca de riesgo en el panel. |

### Pruebas de la interfaz (manuales o con `AppTest`)

Streamlit incluye `streamlit.testing.v1.AppTest` para ejecutar páginas sin navegador. Ejemplo
para renderizar una vista como un usuario concreto (requiere la BD levantada):

```python
from streamlit.testing.v1 import AppTest


def view_script(module_name, root):
    import importlib, sys

    sys.path.insert(0, root)
    importlib.import_module(f"app.views.{module_name}").render()


at = AppTest.from_function(view_script, args=("academics", "/ruta/al/proyecto"))
at.session_state["user_id"] = 3
at.run()
assert not at.exception
print([e.label for e in at.expander])
```

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
  - Las escrituras pasan siempre por `common.run_action(lambda s: …, "mensaje")`.
  - Para modificar el usuario actual se usa `s.merge(user)`.
  - Dentro de un bucle, las lambdas capturan las variables por argumento por defecto
    (`lambda s, iid=item.id: …`).
- **Widgets:** cuando se repiten en una lista, usar `key` únicas con el id del objeto
  (`f"del_i_{item.id}"`).

## Cómo extender la plataforma

### Agregar una página

1. Crear `app/views/nueva.py` con una función `render()` que empiece con
   `user = common.require_user()`.
2. Registrarla en `app/main.py`, dentro del grupo correspondiente:
   `st.Page(nueva.render, title="…", icon="…", url_path="…")`.

### Agregar un campo a una tabla

1. Agregar el `mapped_column` en `app/db/models.py`, con `default=`.
2. Actualizar el servicio (validación) y la vista.
3. Recrear el esquema (`make reset-db`) o crear una migración, si ya se incorporó Alembic.
4. Documentarlo en [Modelo de datos](06-modelo-de-datos.md).

### Agregar una regla de reto automático

1. Agregar una entrada en `_rules()` de `app/services/challenge_rules.py`:
   `"codigo": Rule("Descripción", meta, lambda s, u: medida, "unidad")`.
2. Para que sea un reto global por defecto, agregarlo a `GLOBAL_CHALLENGES` en
   `app/db/init_db.py` y ejecutar `make init-db`, que inserta los retos que falten.
3. También se puede crear desde la UI como admin: *Crear reto → Reto global → Verificación
   automática*.

### Agregar un nuevo tipo de error de dominio

Agregar la clase a la tupla `USER_ERRORS` de `app/ui/common.py`. Así `run_action` la muestra como
mensaje en lugar de dejar que Streamlit muestre la traza del error.

### Agregar un programa al catálogo de pensum

Ver [Datos iniciales](11-datos-iniciales-y-demo.md#agregar-otro-programa-al-catálogo).
