# 9. Páginas y vistas

Cada página es un módulo de `app/views/` con una función `render()`, y `app/main.py` las
registra en `st.navigation`. Esta guía describe qué ve el usuario en cada una, qué acciones puede
hacer, qué servicios usa y qué tablas lee o escribe.

Componentes compartidos (`app/ui/common.py`):

| Componente | Uso |
|------------|-----|
| `current_user()` / `require_user()` | Recargan el usuario autenticado. Si no hay sesión, detienen el render. |
| `run_action(fn, mensaje)` | Ejecuta una escritura en su propia transacción. Ver [Persistencia](07-persistencia.md#escritura-commonrun_action). |
| `flash()` / `show_flashes()` | Avisos tipo *toast* que sobreviven al rerun. |
| `avatar_html()`, `user_chip()` | Foto o iniciales, nombre visible, `@usuario` y un subtítulo. |
| `challenge_ranking_banner()` | Banner del ranking de un reto (participantes, % de éxito, primero en completar, orden). |
| `leaderboard_banner()` | Ranking por puntos (general, de amigos o de un grupo). |
| `fmt_grade()`, `fmt_dt()`, `CATEGORY_LABELS` | Formato de notas, fechas (zona horaria local) y etiquetas de categoría. |
| `enable_sidebar_hover()` | Inyecta `app/ui/sidebar_hover.js`: con el menú lateral oculto, pasar el mouse por el borde izquierdo lo expande. |

### Menú lateral: expandir al pasar el mouse

Cuando el menú lateral está oculto (botón «<<»), una franja invisible de 16 px en el borde
izquierdo de la ventana lo **expande al pasar el mouse**. Al sacar el mouse del menú, este se
vuelve a ocultar tras 0,4 s.

- **Sólo se re-oculta si se abrió por hover.** Si el usuario lo abre con el botón «>>», queda
  fijo como siempre.
- **Usa los botones nativos de Streamlit** (`stExpandSidebarButton` y `stSidebarCollapseButton`).
  Así se respeta el estado interno del menú, incluido el que Streamlit guarda en `localStorage`.
  Los selectores se verificaron en Streamlit 1.66; si una actualización los cambia, el script
  simplemente deja de actuar sin romper la app.
- **Sólo se activa con mouse** (`(hover: hover) and (pointer: fine)`). En pantallas táctiles no
  hace nada.
- **Se inyecta una sola vez por pestaña del navegador** con
  `st.html(..., unsafe_allow_javascript=True)` dentro de `with st.sidebar`. Se protege con
  `window.__ctSidebarHover` porque Streamlit vuelve a ejecutar el script en cada rerun.

---

## 🔐 Ingresar (`views/login.py`)

Es visible sólo sin sesión iniciada. Tiene dos pestañas:

| Pestaña | Campos | Acción |
|---------|--------|--------|
| Iniciar sesión | Usuario o correo, contraseña | `auth.login` → guarda `user_id` en la sesión y muestra "¡Bienvenido…!". |
| Crear cuenta | Nombre, apellido, usuario, correo, contraseña (×2) | Verifica que las contraseñas coincidan → `auth.register` → "Cuenta creada". |

El pie de la página indica el proveedor activo: Keycloak o base de datos local.

**Tablas:** `users` (lectura y escritura); Keycloak, si está activo.

## 🏠 Inicio (`views/home.py`, `/inicio`)

| Sección | Contenido | Servicios |
|---------|-----------|-----------|
| Al cargar | Re-evalúa los retos automáticos; si se completó alguno, muestra un toast y globos 🎈. | `challenges.refresh_automatic` |
| Métricas | Promedio general, promedio del semestre actual, puntos en retos, posición en el ranking, seguidores y seguidos. | `academics.user_summary`, `challenges.leaderboard`, `social.follow_counts` |
| 🏆 Mis retos en curso | Retos abiertos en los que participo y aún no completo, con barra de progreso si tienen regla. | `challenges.list_challenges(scope="joined")`, `challenge_rules.progress` |
| 💬 Últimas discusiones | Las 5 publicaciones más recientes, con conteo de comentarios y "me gusta". | `forum.list_posts` |
| 💌 Apoyos recibidos | Los últimos 5 mensajes. | `social.inbox` |
| 👀 Actividad de quienes sigues | Últimos retos completados por las personas que sigo. | `challenges.following_activity` |

## 💬 Foros (`views/forum.py`, `/foros`)

**Vista de lista:**

- **Botón "Nueva publicación":** abre un diálogo con título, categoría, contenido (Markdown) y
  etiquetas, y llama a `forum.create_post`. Al crearla, abre la publicación nueva.
- **Filtros:** búsqueda de texto, categoría, estado (Todas / Abiertas / Resueltas), orden y el
  interruptor "Sólo de personas que sigo".
- **Tarjetas:** título (con ✅ si está resuelta), insignias de categoría y etiquetas, autor,
  fecha, número de comentarios y de "me gusta", y botón **Abrir**.

**Vista de detalle** (`session_state.post_id`):

- **Encabezado y contenido:** título, insignias, autor y contenido en Markdown.
- **Acciones:**
  - 👍 / 💙: "me gusta", con `forum.toggle_like`.
  - Si soy el autor o un admin: **Marcar resuelta / Reabrir** (`forum.set_solved`) y
    **Eliminar** (`forum.delete_post`).
- **Comentarios:** lista en orden cronológico. Cada comentario tiene botón 🗑️ si soy su autor o
  un admin (`forum.delete_comment`).
- **Responder:** formulario "Escribe una respuesta o comentario", que llama a
  `forum.add_comment`.

**Tablas:** `posts`, `comments`, `post_likes`, `follows` (filtro) y `users`.

## 📚 Plan académico (`views/academics.py`, `/academico`)

### Encabezado

- **Botón "Agregar materia":** abre un diálogo con nombre, código, docente, semestre, créditos,
  estado y **categoría**, y llama a `academics.add_subject`.
- **Expander "⚙️ Datos del plan de estudios"** (abierto si el usuario aún no tiene programa):
  - Un formulario con programa, plan, semestre actual y total de semestres, que llama a
    `users.update_profile`.
  - **Cargar un pensum del catálogo:** un selector de programa y el botón **Cargar pensum**,
    que llama a `academics.load_pensum`. Agrega las materias que falten como "Pendiente".

### Métricas

Promedio general, promedio del semestre actual, créditos aprobados, materias aprobadas y
reprobadas, y semestre actual sobre el total. Debajo, una nota explica cómo se calculan los
promedios.

### Expandir y colapsar todo

Las pestañas «Semestre actual», «Historia académica» y «Plan completo» tienen, arriba a la
derecha, los botones **Expandir todo** y **Colapsar todo**. Abren o cierran de una vez todos los
menús **de esa pestaña**: las tarjetas de materia en las dos primeras y los semestres en «Plan
completo». Así se ve el detalle de cada elemento sin abrirlos uno por uno.

Cómo funciona:

- **Estado en la sesión.** Cada expander tiene una `key` estable: `subject_expander_<id>` para
  las materias y `plan_semester_expander_<n>` para los semestres. Los botones fijan su estado en
  `st.session_state` mediante un callback.
- **Memoria propia para los títulos que cambian.** Streamlit identifica un expander también por
  su título, que aquí incluye notas y promedios. Por eso la vista guarda el estado abierto o
  cerrado en `st.session_state["_academics_open_expanders"]` y lo restaura antes de dibujarlo.
  Así, una materia abierta **sigue abierta** después de agregar o editar un ítem, aunque cambie
  su nota.

### Pestaña "Semestre actual (N)"

Una **tarjeta expandible por materia** del semestre actual. Su título muestra el estado, el
nombre, el código, los créditos y la nota en color: verde si aprueba, rojo si no, gris si aún
no tiene nota. Al expandir:

- **Encabezado:** categoría, docente, semestre y porcentaje ya evaluado.
- **Botones:**
  - **Editar:** diálogo con todos los campos, incluida la categoría.
  - **Cerrar:** sólo si la materia está "cursando" y ya tiene nota. Marca la materia como
    aprobada o reprobada según la nota.
  - **Borrar.**
- **Lista de ítems:** nombre, descripción, nota y porcentaje, con botones ✏️ (diálogo de
  edición) y 🗑️.
- **Formulario "Agregar ítem calificable":** nombre, calificación, porcentaje (0 = sin
  porcentaje), descripción y fecha de entrega.

### Pestaña "Historia académica"

Arriba, las dos gráficas se muestran **lado a lado**, en dos columnas con la misma altura
(320 px):

1. **Izquierda: gráfica de avance de créditos**. Barras horizontales apiladas, en porcentaje del
   plan, por categoría (🔬 Ciencias, 📜 Humanidades, 💻 Tecnología, 🌐 Idiomas) más una barra
   **📊 Total**. La leyenda va debajo, en el orden Aprobados, Cursando, Por cursar.
   - **Azul claro** (`#7CC6F2`): créditos **aprobados**.
   - **Gris** (`#9CA3AF`): créditos que se están **cursando**.
   - Gris muy tenue: créditos por cursar. Al final de la barra se indica el porcentaje cubierto
     y el total de créditos de la categoría.
   - Encima aparece el resumen: *"Avance de créditos · X aprobados + Y cursando de Z (N %)"*.
   - El *hover* muestra los créditos exactos.
2. **Derecha: gráfica de evolución del promedio** por semestre. Una leyenda debajo identifica
   cada línea:
   - **Promedio del semestre**: azul (`#4F46E5`), línea continua con marcadores.
   - **Nota mínima aprobatoria (3)**: rojo (`#DC2626`), punteada.
   - **Promedio general (x.xx)**: verde (`#16A34A`), discontinua.

   Los valores de la leyenda se toman de `GRADE_PASSING` y del promedio general del estudiante.
   Si aún no hay notas, la columna muestra «Aún no hay notas registradas».

Debajo de las gráficas están los botones **Expandir todo / Colapsar todo**, que afectan a las
materias de los semestres anteriores. Siguen los **semestres anteriores al actual**: para cada
uno, un encabezado con su promedio y créditos, y debajo las tarjetas de sus materias (las mismas
de la pestaña "Semestre actual").

En el detalle de estudiante del panel de administrador, la gráfica de avance de créditos se
muestra a todo el ancho.

### Pestaña "Plan completo"

Un **expander por semestre** del plan, del 1 al último registrado. Su título es:

> 📘 **Semestre N** · 📍 actual · M materias · C créditos · A/M aprobadas · promedio P

El marcador "📍 actual" y el promedio sólo aparecen cuando aplican. Al expandirlo se ve la
**tabla de materias** del semestre con nombre, código, categoría, créditos, estado, nota y
cantidad de ítems.

**Tablas:** `subjects`, `grade_items` y `users` (datos del plan).

## 🏆 Retos (`views/challenges.py`, `/retos`)

La página tiene dos columnas (2,2 : 1).

**Columna izquierda: lista de retos.**

- **Controles:**
  - Botón **Crear reto**: abre un diálogo con título, descripción, dificultad, puntos,
    visibilidad y fechas. Un administrador ve además la casilla *Reto global* y el selector de
    *Verificación automática* (regla).
  - Filtro (`segmented_control`) por alcance: Todos, Globales, Comunidad, De quienes sigo,
    Creados por mí, En los que participo.
  - Interruptor **Sólo abiertos**.
- **Tarjeta de reto:**
  - **Contenido:** insignias (Global/Comunidad, puntos, dificultad, 🤖 automático o 📝 con
    evidencia, visibilidad, cerrado), descripción, creador, participantes, completados y
    fechas.
  - **Progreso:** barra de progreso si participo y el reto tiene regla. Mensaje de completado
    con la fecha si ya lo cumplí.
  - **Botones:**
    - **Ver ranking:** lo muestra en el banner derecho.
    - **Unirme.**
    - **Verificar** (retos automáticos) o **Cumplido** (popover con la evidencia).
    - **Abandonar.**
    - **Gestionar** (creador o admin): cerrar o reabrir y eliminar.

**Columna derecha: banners de ranking.**

1. **🏆 Ranking del reto seleccionado:**
   - Participantes, completados y % de éxito.
   - **"🚀 Primero en cumplirlo"**.
   - Hasta 15 participantes en orden de llegada (🥇🥈🥉, #4…) y luego los que siguen ⏳ en
     progreso.
2. **📊 Ranking general:** puntos totales, retos completados y veces que llegó primero. Un
   selector cambia entre *Todos* y *Personas que sigo* ("Ranking entre amigos").

**Tablas:** `challenges`, `challenge_participants`, `follows` y `users`. Las reglas consultan
además `posts`, `comments`, `grade_items`, `subjects` y `support_messages`.

## 👥 Personas (`views/community.py`, `/personas`)

- **Pestañas Explorar, Seguidores y Siguiendo.**
  - *Explorar* incluye una búsqueda por nombre, alias, usuario o programa.
- **Fila de persona:** avatar, nombre, programa y semestre, más estos botones:
  - **Seguir / Dejar de seguir** (`social.follow` / `unfollow`).
  - **Apoyar**: abre el diálogo "Enviar mensaje de apoyo". Los mensajes rápidos (`pills`)
    rellenan el texto, que se puede editar antes de enviar (`social.send_support`).
  - **Perfil.**
- **Perfil público** (`session_state.profile_id`):
  - Foto, nombre, biografía, programa, universidad, ciudad, intereses y enlaces.
  - Métricas: seguidores, siguiendo, semestre, puntos y retos completados.
  - Botones de acción y lista de retos completados.
  - **Las notas y promedios no se muestran a otros estudiantes.**

**Tablas:** `users`, `follows`, `support_messages` y `challenge_participants`.

## 💌 Mensajes de apoyo (`views/messages.py`, `/mensajes`)

- **Recibidos:**
  - Remitente, fecha, marca 🆕 en los no leídos, mensaje y botón **Responder** (abre el mismo
    diálogo de apoyo).
  - Al abrir la página, todos los mensajes quedan marcados como leídos
    (`social.mark_all_read`).
- **Enviados:** destinatario, fecha y mensaje.
- **En el menú lateral:** el título de la página muestra el número de no leídos, p. ej.
  "Mensajes de apoyo (2)".

**Tablas:** `support_messages` y `users`.

## 👤 Mi perfil (`views/profile.py`, `/perfil`)

- **Columna izquierda:**
  - Foto actual, con opciones para **subir** una nueva (png, jpg, jpeg o webp, máx. 5 MB) o
    **quitarla**.
  - Fecha de registro y rol.
- **Pestaña "Datos personales":** nombre y apellido (`auth.change_names`, que también
  sincroniza Keycloak), alias, biografía, teléfono, ciudad, fecha de nacimiento, intereses,
  GitHub y LinkedIn (`users.update_profile`).
- **Pestaña "Datos académicos":** universidad, código estudiantil, programa, plan, semestre
  actual y total de semestres.
- **Pestaña "Cuenta y seguridad":** usuario (sólo lectura), cambio de correo
  (`auth.change_email`) y cambio de contraseña con la actual, la nueva y su confirmación
  (`auth.change_password`).

**Tablas:** `users`; Keycloak, si está activo.

## 🛡️ Panel de administrador (`views/admin.py`, `/admin`)

Sólo está disponible para `role == "admin"`. La página vuelve a verificar el rol y detiene el
render si no corresponde. Tiene cinco pestañas:

| Pestaña | Contenido |
|---------|-----------|
| **Resumen** | 12 métricas globales; gráfica de **actividad de los últimos 30 días**; **histograma** del promedio general con la línea de aprobación; tabla de **estudiantes en riesgo**; tabla de retos con la barra de tasa de éxito. |
| **Estudiante** | Selector de usuario y todo su detalle: datos personales y de cuenta, alerta si está en riesgo, 7 métricas, promedio por semestre (barras), tabla de materias (con categoría), **gráfica de avance de créditos por categoría**, ítems calificados, retos con su evidencia, publicaciones y red social. |
| **Grupos** | Filtros por programa, semestre y estudiantes específicos. Muestra métricas del grupo (cantidad, promedio, en riesgo, retos, publicaciones, apoyos), barras horizontales del promedio por estudiante (rojo si está en riesgo), **ranking del grupo**, tabla completa y descarga en **CSV**. |
| **Contenido** | Selector entre Publicaciones, Comentarios, Retos y Mensajes; tabla completa y eliminación por id. |
| **Usuarios** | Tabla de todos los usuarios; selector para cambiar el rol (estudiante o administrador) y habilitar o deshabilitar la cuenta. Con Keycloak, la cuenta también se deshabilita allá. Un admin no puede cambiar su propio rol ni deshabilitarse a sí mismo. |

**Servicios:** `admin.*`, `academics`, `forum.delete_*`, `challenges.delete_challenge`,
`auth.set_active` y `challenges.leaderboard`. **Tablas:** todas.
