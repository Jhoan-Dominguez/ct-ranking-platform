# CT Ranking — Documentación del proyecto

Plataforma académica y social para estudiantes, construida con **Streamlit**.

> La documentación técnica completa está en [`docs/`](README.md): arquitectura, modelo de
> datos, servicios, páginas, reglas de negocio, despliegue y solución de problemas. Este archivo
> resume qué se construyó y qué se agregó respecto al enunciado. Los estudiantes
discuten en foros, llevan su plan de estudios con notas y promedios, compiten en retos y se apoyan
entre sí. Un panel de administrador permite hacer seguimiento a un estudiante o a un grupo.

## 1. Arquitectura

```
┌────────────────────┐   ROPC / Admin API   ┌──────────────────────┐
│ Streamlit (app/)   │ ───────────────────► │ Keycloak 26 (docker) │
│  pages → services  │                      │  realm ct-ranking    │
│        ↓           │                      └──────────┬───────────┘
│   SQLAlchemy 2     │                                 │ BD "keycloak"
└─────────┬──────────┘                                 ▼
          │ BD "ctranking"            ┌────────────────────────────┐
          └─────────────────────────► │ PostgreSQL 16 (docker)     │
                                      └────────────────────────────┘
```

| Capa | Carpeta | Responsabilidad |
|------|---------|-----------------|
| Configuración | `app/core/config.py` | Lee `.env` (BD, Keycloak, escala de notas). |
| Datos | `app/db/` | Modelos ORM (`models.py`), sesión (`session.py`), creación del esquema y datos base (`init_db.py`), datos demo (`demo_data.py`). |
| Lógica de negocio | `app/services/` | Reglas y validaciones, sin dependencias de Streamlit. Es lo que cubren las pruebas. |
| Interfaz | `app/ui/pages/`, `app/ui/` | Una vista por página y componentes compartidos (avatares, banners de ranking, `run_action`). |
| Entrada | `app/main.py` | Navegación (`st.navigation`), barra lateral y control de sesión. |

**Patrón de escritura en la UI:** cada acción del usuario se ejecuta con
`actions.run_action(fn, mensaje)` (`app/ui/components/actions.py`), que abre su propia transacción. Si la acción lanza un error de
negocio, se muestra el mensaje. Si todo va bien, se programa un aviso (toast) y la página se
recarga.

### Autenticación

El enunciado pide un login básico, opcionalmente con Keycloak. Se implementaron dos proveedores
intercambiables con `AUTH_PROVIDER`:

- **`keycloak`** (por defecto):
  - El login usa el flujo *Direct Access Grants* contra el realm `ct-ranking`.
  - El registro y los cambios de contraseña, correo y nombre usan la API de administración de
    Keycloak, con la cuenta de servicio del cliente `ct-ranking-app`.
  - El realm se importa automáticamente desde `docker/keycloak/ct-ranking-realm.json`. Ese archivo
    define el cliente, los roles `student`/`admin` y el usuario administrador.
  - La BD de la app guarda el perfil y el `keycloak_id`, nunca la contraseña.
  - Si Keycloak entrega el rol `admin`, el usuario se vuelve administrador. Las promociones hechas
    desde el panel también se conservan.
- **`local`**: contraseñas con bcrypt en PostgreSQL. Lo usan las pruebas y sirve como alternativa
  sin Keycloak.

## 2. Funcionalidades

### Foros de discusión (💬 Foros)
- **Publicaciones:**
  - Cada una tiene título, categoría (duda académica, problemática, proyecto, recursos…),
    contenido en Markdown y etiquetas.
  - Los demás usuarios responden con **comentarios** en la vista de detalle.
  - Hay búsqueda por texto y filtros por categoría, estado (abiertas o resueltas) y "sólo de
    personas que sigo".
  - Se pueden ordenar por recientes, más comentadas o más valoradas.
- **Gestión:**
  - Cualquier usuario puede dar "me gusta".
  - El autor puede marcar su publicación como **resuelta**.
  - El autor o un administrador pueden eliminar publicaciones y comentarios.

### Perfil personalizable (👤 Mi perfil)
- **Datos que pide el enunciado:** nombre y apellido, alias (único), correo, contraseña e
  **imagen de perfil**.
- **Foto:** se recorta y redimensiona a 256 px. Sin foto, se muestra un avatar con las iniciales.
- **Datos adicionales:**
  - Biografía, teléfono, ciudad y fecha de nacimiento.
  - Universidad, código estudiantil y programa.
  - Intereses, GitHub y LinkedIn.
- **Sincronización:** con Keycloak, los cambios de correo, nombre y contraseña también se aplican
  allá. Para cambiar la contraseña se valida antes la actual.

### Plan académico (📚 Plan académico)
- **Datos del plan:** programa, versión del plan de estudios, semestre actual y total de semestres.
- **Cargar pensum:** carga de un clic del pensum de **Ingeniería de Software**
  (`docs/pensum.png`: 9 semestres, 60 materias, 148 créditos). Las materias quedan como
  *pendientes*.
- **Materias:**
  - Cada una tiene semestre, créditos, código, docente, **categoría** (ciencias, humanidades,
    tecnología o idiomas) y estado: *pendiente* (planeada), *cursando*, *aprobada* o
    *reprobada*.
  - Con esos estados se arma el plan completo y la **historia académica**.
- **Pestaña "Plan completo":** un menú desplegable por semestre (nombre del semestre, materias,
  créditos, aprobadas y promedio). Dentro está la tabla con el detalle de sus materias.
- **Ítems calificables:**
  - Cada materia admite ítems con nombre, descripción, calificación, fecha y **porcentaje
    opcional**.
  - Se pueden agregar, editar y eliminar.
- **Promedios:**
  - **Nota de la materia:** promedio ponderado por porcentaje si todos los ítems lo tienen. El
    resultado se normaliza (nota acumulada). Si no, se usa el promedio simple. También se muestra
    el porcentaje ya evaluado.
  - **Promedio del semestre:** ponderado por créditos sobre las materias vistas con nota.
  - **Promedio general (acumulado):** ponderado por créditos sobre todas las materias vistas con
    nota.
- **Apoyos visuales:**
  - El botón **"Cerrar"** sugiere marcar la materia como aprobada o reprobada según la nota.
  - En "Historia académica" hay dos gráficas **lado a lado**:
    - **Avance de créditos:** por categoría y en total, el % de créditos del plan
      **aprobados (azul claro)** y **en curso (gris)**. Las materias repetidas cuentan una
      sola vez.
    - **Evolución del promedio:** promedio por semestre, con una **leyenda** que identifica
      cada línea (promedio del semestre, nota mínima aprobatoria y promedio general).
  - Botones **"Expandir todo" / "Colapsar todo"** en cada pestaña, para ver de inmediato el
    detalle de todas las materias o semestres. Las materias abiertas siguen abiertas aunque cambie
    su nota.
- La escala de notas se configura en `.env` (`GRADE_MIN`, `GRADE_MAX`, `GRADE_PASSING`). Por
  defecto es 0–5 y se aprueba con 3.

### Retos dinámicos (🏆 Retos)
- **Retos globales:**
  - Son los mismos para todos los usuarios, antiguos y nuevos.
  - Se crean al inicializar la BD (10 retos) y el administrador puede crear más.
  - Se **verifican automáticamente** con reglas (`app/services/challenge_rules.py`), por ejemplo
    publicar en el foro, registrar 10 notas, seguir a 3 compañeros o alcanzar el 80 % de la escala
    en el promedio.
  - Las reglas miden toda la historia del usuario. Por eso un usuario antiguo que ya cumple la
    condición completa el reto al unirse.
- **Retos de la comunidad:**
  - Cualquier estudiante los crea, con dificultad, puntos, fechas de inicio y cierre, y
    visibilidad *pública* o *sólo seguidores*.
  - Los demás se **suscriben** ("Unirme") y los marcan como cumplidos aportando **evidencia**.
- **Banner de ranking a la derecha:**
  - Para el reto seleccionado muestra participantes, cuántos lo completaron, tasa de éxito,
    **quién lo cumplió primero** y el orden de llegada con medallas.
  - Debajo está el **ranking general** de puntos, o el de *personas que sigo*.
  - Quien completa primero un reto recibe **+50 % de bonus** en puntos.
- **Gestión:** el creador o un administrador pueden cerrar, reabrir y eliminar un reto.

### Seguidores y mensajes de apoyo (👥 Personas, 💌 Mensajes)
- **Personas:**
  - Se buscan por nombre, alias, usuario o programa.
  - Se puede **seguir** y **dejar de seguir**, y ver las listas de seguidores y seguidos.
  - Cada usuario tiene un perfil público con sus retos completados. Las notas no se muestran: son
    privadas.
- **Relación con los retos:**
  - Los seguidores ven los retos de visibilidad "sólo seguidores".
  - Hay un filtro de retos "De quienes sigo" y un ranking entre amigos.
  - El inicio muestra la actividad de las personas que sigues.
- **Mensajes de apoyo:**
  - Hay plantillas rápidas ("¡Vamos, tú puedes!", "No te rindas"…) o se escribe un texto libre.
  - Tienen bandeja de recibidos y enviados, y se pueden responder.
  - El menú muestra el contador de mensajes no leídos.

### Panel de administrador (🛡️ sólo rol admin)
- **Resumen:**
  - Métricas globales: usuarios, activos en 7 días, publicaciones, retos, tasa de éxito, notas…
  - Gráfica de actividad de los últimos 30 días e histograma de promedios.
  - Lista de **estudiantes en riesgo**: promedio general o del semestre por debajo de la nota
    mínima.
  - Tabla de retos con su tasa de éxito.
- **Estudiante:**
  - Toda la información de un usuario: perfil, promedios, créditos, materias e ítems.
  - Promedio por semestre, retos con su evidencia, publicaciones, seguidores y apoyos.
  - Alerta si el estudiante está en riesgo.
- **Grupos:**
  - Se filtra por programa, semestre o por estudiantes específicos.
  - Muestra el promedio del grupo, cuántos están en riesgo, la participación, una gráfica
    comparativa y el ranking del grupo.
  - El resultado se puede exportar a **CSV**.
- **Contenido:** ver todas las publicaciones, comentarios, retos y mensajes, y eliminarlos
  (moderación).
- **Reportes:** revisar los reportes de los estudiantes y resolverlos, descartarlos, eliminar el
  contenido reportado o deshabilitar al usuario.
- **Usuarios:** cambiar el rol y habilitar o deshabilitar cuentas. Con Keycloak, el cambio de
  estado también se aplica allá. También se ve si el correo está verificado y si la cuenta tiene
  eliminación programada (y se puede cancelar).

### Cuentas, seguridad y moderación
- **Activación por correo:** al registrarse, Keycloak envía un enlace. Hasta abrirlo no se puede
  iniciar sesión, y desde el login se puede reenviar.
- **Verificación en dos pasos (2FA con QR):** nativa de Keycloak, sin servicios externos.
  - Se activa desde Mi perfil: llega un enlace por correo a la página de Keycloak con el QR para
    Google Authenticator, Microsoft Authenticator o FreeOTP.
  - Luego el login pide el código.
- **Eliminar la cuenta:**
  - Requiere la contraseña (+ código 2FA) y un código de 6 dígitos enviado al correo.
  - La cuenta queda **desactivada y oculta 7 días**: al iniciar sesión sólo se puede cancelar.
  - Al vencer el plazo, se borra de la app y de Keycloak.
- **Bloquear y reportar** usuarios, publicaciones y comentarios. Los reportes llegan al panel de
  administrador.
- **Correo:**
  - En desarrollo, **Mailpit** atrapa todos los correos y los muestra en
    http://localhost:8025.
  - En producción se usa un SMTP real.
- Detalle completo en [`docs/14-cuentas-seguridad-y-moderacion.md`](14-cuentas-seguridad-y-moderacion.md).

### Inicio (🏠)
- Promedios, puntos y posición en el ranking.
- Retos en curso con su barra de progreso.
- Últimas discusiones, apoyos recibidos y actividad de las personas que sigues.
- Al entrar se re-evalúan los retos automáticos y se celebra cada uno completado.

## 3. Qué se agregó además de lo solicitado

- Verificación **automática** de retos globales mediante reglas, y bonus por llegar primero.
- Retos con **fechas**, **dificultad**, **visibilidad sólo para seguidores** y estado
  abierto/cerrado.
- **Rankings** general, entre amigos y por grupo (en el panel de administrador).
- Foro con **categorías, etiquetas, "me gusta", estado resuelto**, búsqueda y orden.
- **Créditos** y **porcentajes** en el cálculo de promedios, porcentaje evaluado y sugerencia de
  cierre de materia.
- Detección de **estudiantes en riesgo** y exportación CSV de grupos.
- **Catálogo de pensum**, **categorías de materias** y **avance de créditos por categoría**,
  también visible en el detalle de estudiante del panel de administrador.
- Perfil público con logros, y avatar con iniciales por defecto.
- Menú lateral que, estando oculto, **se expande al pasar el mouse** por el borde izquierdo y se
  vuelve a ocultar al salir de él.
- Plantillas de mensajes de apoyo y contador de no leídos.
- **Activación de cuentas por correo**, **2FA con QR**, **eliminación diferida de cuentas** con
  doble verificación, y **reportes y bloqueos** con gestión desde el panel de administrador.
- Proveedor de autenticación **local** alternativo a Keycloak.
- **Correo institucional obligatorio** (`@estudiantes.areandina.edu.co`) e **inicio de sesión con
  Google** para cuentas institucionales (gratuito, vía Keycloak).
- **Datos de demostración** (`make seed-demo`). Ocho estudiantes de Ingeniería de Software en
  distintos niveles: recién ingresados (semestre 1), iniciando (2–3), a mitad de carrera (5–6) y
  a punto de terminar (8–9). Tienen historia académica completa con notas, materias repetidas y
  un estudiante en riesgo.
- **Pruebas automatizadas** con pytest sobre SQLite en memoria (`make test`).

## 4. Cómo ejecutarlo

Requisitos: Docker con Docker Compose, Python 3.12+ y `make`.

```bash
make create      # .env, dependencias en .venv y hooks de pre-commit
make up          # PostgreSQL + Keycloak + Mailpit, configura Keycloak y crea las tablas
make seed-demo   # (opcional) usuarios y datos de ejemplo
make run         # http://localhost:8501
make down        # detiene los contenedores (conserva datos)
```

**Accesos:**

| Qué | Dónde / credenciales |
|-----|----------------------|
| App, administrador | `admin` / `Admin123!` (configurable en `.env`) |
| App, usuarios demo | `diego.lopez`, `valentina.rios` (sem. 1), `carlos.ruiz` (2), `sofia.herrera` (3), `laura.gomez` (5), `mateo.castro` (6), `juan.perez` (8), `ana.martinez` (9) / `Demo1234` |
| Consola de Keycloak | http://localhost:8180 → `admin` / `admin` |
| Correos (Mailpit) | http://localhost:8025 |

**Otros comandos** (`make help`):

| Comando | Qué hace |
|---------|----------|
| `make dev` | `up` + `run`. |
| `make logs` | Muestra los logs de los contenedores. |
| `make ps` | Muestra el estado de los contenedores. |
| `make test` | Ejecuta las pruebas. |
| `make lint` | Ejecuta pre-commit (isort, ruff y chequeos básicos) sobre todo el repo. |
| `make format` | Ordena imports y formatea el código. |
| `make reset-db` | Recrea las tablas de la app. |
| `make purge-accounts` | Borra definitivamente las cuentas cuyo plazo de eliminación venció. |
| `make migrate-emails` | Pasa el correo de los estudiantes al dominio institucional (`ARGS=--dry-run` para simular). |
| `make destroy` | Baja todo y **borra los volúmenes**. |

> Si el puerto 8180 o el 5432 están ocupados, cambia `KEYCLOAK_PORT` y `KEYCLOAK_URL`, o
> `POSTGRES_PORT`, en `.env`.

**Calidad de código:**
- `pre-commit` ejecuta **isort** (perfil black), **ruff check** (con `--fix`) y **ruff format**,
  además de hooks de higiene (YAML, JSON, TOML, espacios finales, archivos grandes).
- La configuración está en `pyproject.toml` y `.pre-commit-config.yaml`.

## 5. Limitaciones conocidas e ideas futuras

- La sesión vive en `st.session_state`: al recargar el navegador hay que volver a iniciar sesión.
  Una mejora sería usar el flujo *Authorization Code* de Keycloak con `st.login` (OIDC) y cookies.
- El esquema se crea con `create_all`. Las columnas nuevas se agregan con sentencias
  idempotentes (`COLUMN_UPGRADES` en `init_db`). Para cambios más complejos en producción
  conviene usar **Alembic**.
- El 2FA y la activación por correo sólo funcionan con `AUTH_PROVIDER=keycloak`. El proveedor
  local no los tiene.
- El pensum no indica créditos. Los créditos y categorías se asignaron como estimación en
  `app/database/seeds/pensums.py`.
- La evidencia de retos manuales es auto-declarada. Se podría agregar la validación del creador
  del reto.
- **Otras ideas:**
  - Notificaciones de nuevos comentarios.
  - Adjuntar archivos en el foro.
  - Grupos de estudio.
  - Importar el pensum desde un CSV.
