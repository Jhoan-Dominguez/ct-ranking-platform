# 8. Servicios (lógica de negocio)

La lógica de negocio está en `app/services/` (un módulo por dominio). La identidad está en el
paquete `app/auth/` y el correo en `app/core/mailer.py`. Todos comparten varias convenciones:

- Reciben una `Session` como primer argumento y **no** hacen `commit`. El commit lo hace
  `session_scope()`.
- Validan los datos y lanzan una excepción de dominio con un mensaje en español.
- Verifican la **propiedad**: un estudiante sólo puede modificar sus propios datos. Las
  funciones de administración reciben al `actor` y comprueban que sea admin, aunque la página
  ya lo haya verificado.
- No importan Streamlit.

| Módulo | Excepción | Responsabilidad |
|--------|-----------|-----------------|
| `app/auth/` (paquete) | `AuthError` | Login, registro, credenciales, 2FA y Google (Keycloak o local). |
| `users.py` | `ProfileError` | Perfil, avatar y búsqueda de personas. |
| `forum.py` | `ForumError` | Publicaciones, comentarios y "me gusta". |
| `social.py` | `SocialError` | Seguidores y mensajes de apoyo. |
| `academics.py` | `AcademicError` | Materias, ítems, promedios, créditos y pensum. |
| `challenges.py` | `ChallengeError` | Retos, participación, ranking y leaderboard. |
| `challenge_rules.py` | — | Reglas de verificación automática. |
| `admin.py` | `AdminError` | Métricas, consultas y gestión del panel de administrador. |
| `app/auth/accounts.py` | `AccountError` (`InvalidCodeError`) | Eliminación diferida de cuentas, cambio de correo verificado y purga. |
| `moderation.py` | `ModerationError` | Bloqueos entre usuarios y reportes. |
| `app/core/mailer.py` | `MailError` | Envío de correos de la app (SMTP o memoria). |
| `app/core/ratelimit.py` | `RateLimitError` (o la que reciba) | Límite de intentos en memoria: login local, reenvío de correos de Keycloak. |

---

## `app/auth/` (autenticación)

Ver el detalle en [Autenticación](05-autenticacion.md). El paquete se divide en:

| Módulo | Contenido |
|--------|-----------|
| `service.py` | API pública (lo que reexporta `app/auth/__init__.py`). |
| `keycloak.py` | `KeycloakClient` e `Identity`: login por contraseña, API de administración, correos y credenciales OTP. `password_login(..., password_only=True)` usa el cliente `ct-ranking-pwcheck` (paso 1 del login), y `delete_broker_only_user` borra usuarios creados sólo por Google. Reutiliza las conexiones HTTP (`requests.Session`) y guarda en caché el token de la cuenta de servicio hasta poco antes de que venza. |
| `validation.py` | Usuario, correo, dominio institucional, nombres y contraseña. |
| `passwords.py` | `hash_password` y `check_password` (bcrypt). |
| `errors.py` | `AuthError`, `EmailNotVerifiedError`, `AccountNotFoundError` (Google sin cuenta) e `INVALID_LOGIN`. |
| `accounts.py` | Eliminación diferida y cambio de correo (ver más abajo). |

| Función | Descripción |
|---------|-------------|
| `validate_username/email/names/password` | Validaciones reutilizables. |
| `student_domain()`, `student_email(local)`, `validate_student_email(email)` | Dominio institucional obligatorio para estudiantes: arma el correo a partir de la parte local y lo valida. |
| `hash_password`, `check_password` | bcrypt. |
| `KeycloakClient` | `password_login`, `create_user`, `reset_password`, `update_user`, `set_enabled`. |
| `login`, `register`, `change_password`, `change_names`, `set_active` | API pública, independiente del proveedor. |
| `validate_new_email(session, user, email)`, `apply_verified_email(session, user, email)` | Validan y aplican un correo nuevo. `apply_verified_email` sólo se llama después de comprobar el código enviado a ese correo (`accounts.confirm_email_change`). |

## `users.py`

| Función | Descripción |
|---------|-------------|
| `get_user(session, user_id)`, `list_users(session)` | Usuario por id; todos los usuarios ordenados por username. |
| `avatar_bytes(session, user_id)` | La foto (columna diferida) sin cargar el resto de la fila. |
| `update_profile(session, user, **fields)` | Actualiza los campos permitidos (`PROFILE_FIELDS`: alias, bio, phone, city, university, student_code, interests, github_url, linkedin_url, program, study_plan), cada uno con su longitud máxima. También `birth_date` (no futura) y `current_semester`/`total_semesters` (1 ≤ actual ≤ total ≤ 20). El alias es único sin distinguir mayúsculas. `github_url` y `linkedin_url` deben ser enlaces `http(s)://` con dominio (se rechazan `javascript:` y caracteres que rompan el Markdown). |
| `process_avatar(raw)` | Valida que sea imagen y pese ≤ 5 MB; la recorta al centro en cuadrado, la redimensiona a 256×256 y devuelve PNG. |
| `set_avatar(user, raw \| None)` | Guarda la imagen procesada, o la elimina si recibe `None`. Actualiza `avatar_updated_at`. |
| `search_users(session, query, *, exclude_id, hidden_ids, limit=50)` | Usuarios activos, con el correo verificado y sin eliminación programada, cuyo username, alias, nombre, apellido o programa contienen el texto. `hidden_ids` excluye, por ejemplo, a los usuarios bloqueados. |

## `forum.py`

| Función | Descripción |
|---------|-------------|
| `CATEGORIES` | Lista de categorías válidas. |
| `ORDERINGS` | `{"Más recientes": "recent", "Más comentadas": "comments", "Más valoradas": "likes"}`. |
| `create_post(session, author_id, *, title, body, category, tags)` | Título de 5 a 200 caracteres, cuerpo no vacío y categoría válida. Las etiquetas se normalizan a minúsculas. |
| `list_posts(session, *, search, category, solved, author_ids, exclude_author_ids, order, limit)` | Devuelve `PostRow(post, comments, likes)`. Busca en título, cuerpo y etiquetas. Los conteos tampoco incluyen comentarios ni "me gusta" de `exclude_author_ids`. |
| `get_post(session, post_id)` | Publicación con autor, comentarios (con autor) y "me gusta" ya cargados. |
| `add_comment(session, post_id, author_id, body)` | Comentario de 1 a 5000 caracteres. |
| `delete_post` / `delete_comment(session, actor, id)` | Sólo el autor o un admin. |
| `set_solved(session, actor, post_id, solved)` | Sólo el autor o un admin. |
| `toggle_like(session, post_id, user_id) -> bool` | Da o quita el "me gusta". Devuelve el estado final. |

## `social.py`

| Función | Descripción |
|---------|-------------|
| `follow` / `unfollow(session, follower_id, followed_id)` | `follow` es idempotente. No permite seguirse a sí mismo ni seguir a alguien con quien hay un bloqueo. |
| `is_following`, `following_ids`, `followers`, `following`, `follow_counts` | Consultas de la red: `follow_counts(session, user_id, hidden_ids=None)` devuelve (seguidores, seguidos) sin contar `hidden_ids`. |
| `SUPPORT_TEMPLATES` | Mensajes rápidos: "¡Vamos, tú puedes! 💪", "No te rindas…", etc. |
| `send_support(session, sender_id, recipient_id, message)` | Mensaje de 1 a 500 caracteres a otro usuario existente. |
| `inbox`, `sent(session, user_id, limit=100)` | Mensajes recibidos y enviados, con el remitente o destinatario ya cargado. `inbox` y `unread_count` excluyen a los usuarios bloqueados y a las cuentas en eliminación. `send_support` rechaza el envío si hay un bloqueo. |
| `unread_count`, `mark_all_read` | Contador de no leídos y marcado masivo como leídos. |

## `academics.py`

### Cálculos puros (sin BD)

| Función | Descripción |
|---------|-------------|
| `subject_grade(items)` | Nota de una materia (ponderada y normalizada, o simple). |
| `weighted_progress(items)` | Porcentaje de la nota ya evaluado (suma de pesos, máx. 100). |
| `credit_weighted_average(pairs)` | Promedio ponderado por créditos, ignorando las materias sin nota. |
| `semester_average(subjects, n)`, `general_average(subjects)` | Promedios del semestre y general. |
| `summarize(subjects, current_semester) -> AcademicSummary` | Promedio general, promedio del semestre actual, resumen por semestre (`SemesterSummary`), créditos aprobados y conteo por estado. |
| `credit_progress(subjects) -> list[CreditProgress]` | Créditos totales, aprobados y en curso por categoría, más una fila `total`. Cuenta las materias repetidas una sola vez. |
| `suggested_status(grade)` | `aprobada` si la nota ≥ `GRADE_PASSING`; si no, `reprobada`. |

### Persistencia

| Función | Descripción |
|---------|-------------|
| `list_subjects(session, user_id)` | Materias con sus ítems, ordenadas por semestre y nombre. |
| `user_summary(session, user_id, current_semester)` | `summarize` sobre las materias del usuario. |
| `add_subject(session, user_id, *, name, semester, credits, status, category, code, teacher)` | Valida nombre, créditos ≥ 0, semestre ≥ 1, estado y categoría. |
| `update_subject(session, user_id, subject_id, **fields)` | Sólo el dueño. Mismas validaciones. |
| `delete_subject(session, user_id, subject_id)` | Sólo el dueño. Borra también sus ítems. |
| `load_pensum(session, user, program) -> int` | Copia al plan las materias del catálogo que falten (comparando por código o nombre) como `pendiente`. Actualiza `program`, `study_plan` y `total_semesters`. Devuelve cuántas materias agregó. |
| `add_item(session, user_id, subject_id, *, name, grade, description, weight, delivered_on)` | Nota dentro de la escala. Porcentaje opcional de 0 a 100, y la suma de porcentajes de la materia no puede pasar de 100. |
| `update_item`, `delete_item` | Sólo el dueño de la materia. |

## `challenges.py`

| Función | Descripción |
|---------|-------------|
| `SCOPES` | Filtros de la UI: Todos, Globales, Comunidad, De quienes sigo, Creados por mí, En los que participo. |
| `create_challenge(session, creator, *, title, description, difficulty, points, visibility, starts_at, ends_at, kind, rule)` | Valida los datos. `kind=global` sólo lo puede crear un admin, y un reto global siempre es público. `rule` debe existir en `RULES`. |
| `list_challenges(session, user, *, scope, only_open, hidden_creator_ids) -> list[ChallengeRow]` | Retos visibles con conteo de participantes y completados (calculados en SQL), más la participación del usuario. |
| `get_challenge(session, challenge_id)` | Reto por id. |
| `is_open(challenge)` | Activo y dentro de la ventana `starts_at`–`ends_at`. |
| `join(session, user, challenge_id)` | Une al usuario si el reto es visible y está abierto. Es idempotente. Si el reto tiene regla y ya se cumple, lo completa al instante. |
| `leave(session, user, challenge_id)` | No se puede abandonar un reto ya completado. |
| `complete(session, user, challenge_id, evidence)` | Con regla: verifica la meta. Sin regla: exige evidencia. Marca `completed_at`. |
| `refresh_automatic(session, user) -> list[str]` | Completa los retos con regla que el usuario ya cumple y devuelve sus títulos. Se llama en Inicio y en Retos. |
| `ranking(session, challenge_id) -> list[RankingEntry]` | Primero quienes completaron (por `completed_at`, con posición), luego los pendientes (por `joined_at`). |
| `stats(session, challenge_id, entries=None) -> ChallengeStats` | Participantes, completados, primero en completar y tasa de éxito. Acepta el resultado de `ranking` para no repetir la consulta. |
| `leaderboard(session, *, limit, user_ids, exclude_ids) -> list[LeaderboardEntry]` | Puntaje total, retos completados y cantidad de veces que llegó primero. Se calcula en SQL con `LIMIT`. |
| `standing(session, user_id) -> Standing` | Puntaje, retos completados y posición de un usuario, sin cargar todo el ranking (Inicio y perfil público). |
| `scores_by_user(session) -> dict[int, int]` | Puntaje de cada usuario (tabla del panel). |
| `set_active`, `delete_challenge(session, actor, id, …)` | Sólo el creador o un admin. |
| `following_activity(session, user, limit)` | Últimos retos completados por las personas que sigo. |
| `completed_by(session, user_id)` | Retos completados por un usuario (perfil público). |

## `challenge_rules.py`

`RULES: dict[str, Rule]`. Cada `Rule` tiene `label`, `target`, `unit` y una función
`measure(session, user_id) -> float`.

| Código | Meta | Mide |
|--------|------|------|
| `first_post` | 1 | Publicaciones del usuario. |
| `forum_helper` | 5 | Comentarios en publicaciones **de otros**. |
| `grades_10` | 10 | Ítems calificables registrados. |
| `plan_5` | 5 | Materias en el plan. |
| `first_pass` | 1 | Materias aprobadas. |
| `high_average` | 80 % de `GRADE_MAX` (4,0 en escala 0–5) | Promedio general. |
| `social_3` | 3 | Personas que sigue. |
| `supporter_5` | 5 | Mensajes de apoyo enviados. |
| `creator` | 1 | Retos creados. |
| `profile_complete` | 4 | Campos completados entre alias, foto, programa y biografía. |

Funciones: `progress(session, code, user_id) -> (actual, meta)` e `is_satisfied(...)`. Un código
que ya no existe en `RULES` (p. ej. una regla renombrada) devuelve `(0, 1)` y se muestra como no
cumplido, en lugar de romper Inicio y Retos.

## `admin.py`

| Función | Devuelve |
|---------|----------|
| `global_metrics(session) -> GlobalMetrics` | Usuarios, activos en 7 días, nuevos en 30 días, publicaciones, comentarios, retos globales y de comunidad, participaciones, completados, mensajes, seguimientos, notas, reportes pendientes, cuentas por eliminar y cuentas sin activar. Todo en una sola consulta. |
| `students_frame(session, user_ids=None) -> DataFrame` | Una fila por usuario con los promedios, materias por estado, créditos aprobados, publicaciones, comentarios, retos completados, puntos, seguidores, apoyos recibidos, último ingreso y la marca `en_riesgo`. Incluye además `verificado`, `eliminacion_programada` y `reportes_recibidos`. |
| `activity_frame(session, days=30) -> DataFrame` | Conteo diario de publicaciones, comentarios, retos completados y mensajes, agrupado por día en SQL. |
| `user_detail(session, user_id) -> UserDetail` | Usuario, materias, resumen académico, seguidores, seguidos, publicaciones, participaciones y mensajes recibidos y enviados. |
| `challenges_frame`, `posts_frame`, `comments_frame`, `messages_frame` | Tablas de contenido para moderar. |
| `set_role(session, actor, user_id, role)`, `delete_message(session, actor, id)` | Gestión. Exigen que `actor` sea admin; nadie puede cambiar su propio rol. |

## `app/auth/accounts.py`

| Función | Descripción |
|---------|-------------|
| `request_deletion(session, user, password, otp=None)` | Re-autentica (contraseña + 2FA), invalida los códigos anteriores y envía por correo un código de 6 dígitos válido 15 min. Entre dos códigos debe pasar al menos un minuto. |
| `confirm_deletion(session, user, code) -> datetime` | Valida el código (máx. 5 intentos) y programa la eliminación en `ACCOUNT_DELETION_DAYS` días. Envía un aviso por correo. Un código incorrecto lanza `InvalidCodeError`, que guarda el intento aunque la acción falle. |
| `request_email_change(session, user, email) -> str` | Valida el correo nuevo y le envía un código de 6 dígitos. El correo todavía no cambia. |
| `confirm_email_change(session, user, code) -> str` | Valida el código, vuelve a comprobar que el correo siga libre, lo aplica (en Keycloak queda verificado) y avisa al correo anterior. |
| `cancel_deletion(session, user)` | Revierte la solicitud y avisa por correo. |
| `pending_deletion_ids(session)` | Ids de las cuentas con eliminación programada (se ocultan en la plataforma). |
| `purge_due_accounts(session, now=None) -> list[str]` | Borra en la app y en Keycloak las cuentas vencidas, cada una en un *savepoint*: si Keycloak falla, esa cuenta se revierte y se reintenta después. Borra los retos de la comunidad del usuario y conserva los globales. Lo usan `app/jobs/purge_accounts.py` y `make purge-accounts`. |

## `moderation.py`

| Función | Descripción |
|---------|-------------|
| `block` / `unblock(session, blocker_id, blocked_id)` | Bloquear borra los seguimientos entre ambos. No se puede bloquear a uno mismo. |
| `has_blocked`, `is_blocked_between`, `blocked_ids`, `blocked_users` | Consultas de bloqueo. `blocked_ids` considera ambas direcciones. |
| `hidden_user_ids(session, viewer_id)` | Bloqueos (en ambas direcciones) + cuentas en eliminación. Las vistas lo usan para ocultar contenido y para los conteos de seguidores, comentarios y "me gusta". |
| `report(session, reporter_id, reported_id, *, reason, description, post_id, comment_id)` | Crea un reporte. Valida el motivo y la descripción, que no apunte a la vez a una publicación y a un comentario, y evita los duplicados pendientes. |
| `list_reports(session, status=None)`, `pending_reports_count`, `reports_against_count`, `reports_against_counts` | Consultas para el panel. `reports_against_counts` devuelve los reportes de todos los usuarios en una sola consulta. |
| `close_report(session, admin, report_id, status, note)` | Resuelve o descarta un reporte (sólo administradores). |
| `REASON_LABELS`, `STATUS_LABELS` | Etiquetas en español para la UI. |

## `app/core/mailer.py`

`send(to, subject, paragraphs)` envía un correo multiparte (texto + HTML) por SMTP (`SMTP_*`).
Con `MAIL_BACKEND=memory` lo guarda en `OUTBOX`. Si el envío falla, lanza `MailError`.

## `app/jobs/purge_accounts.py`

- `run_once()` ejecuta la purga en una transacción.
- `start_background_purge()` inicia, una vez por proceso, un hilo *daemon* que la repite cada
  hora.
- `python -m app.jobs.purge_accounts` la ejecuta una vez desde la línea de comandos.

## Catálogo `app/database/seeds/pensums.py`

| Elemento | Descripción |
|----------|-------------|
| `PlanSubject(semester, code, name, credits, category)` | Una materia del pensum. |
| `Pensum(program, plan, semesters, subjects)` | Un pensum completo, con la propiedad `total_credits`. |
| `SOFTWARE_ENGINEERING` | El pensum de Ingeniería de Software. Ver [Datos iniciales](11-datos-iniciales-y-demo.md#pensum-de-ingeniería-de-software). |
| `PENSUMS` | Diccionario `programa → Pensum`. Lo usan el selector de la UI y `load_pensum`. |
