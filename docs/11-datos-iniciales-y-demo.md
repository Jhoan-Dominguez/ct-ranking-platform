# 11. Datos iniciales, pensum y datos de demostración

## Datos base (`make up` / `make init-db`)

`app/db/init_db.py` → `seed_base()` es **idempotente** y crea:

1. **Usuario administrador.**
   - Se crea con `APP_ADMIN_USERNAME`, `APP_ADMIN_EMAIL`, nombre "Administrador CT" y
     `role=admin`.
   - Con `AUTH_PROVIDER=local` se le asigna además el hash de `APP_ADMIN_PASSWORD`.
   - Con Keycloak, el usuario ya existe en el realm importado. La fila local se vincula a él
     (`keycloak_id`) en su primer login.
2. **Diez retos globales** con verificación automática. Se identifican por su regla, así que no
   se duplican:

| Título | Regla | Dificultad | Puntos |
|--------|-------|------------|--------|
| Rompe el hielo | `first_post` | fácil | 10 |
| Arquitecto de tu carrera | `plan_5` | fácil | 10 |
| Perfil al 100% | `profile_complete` | fácil | 10 |
| Red de apoyo | `social_3` | fácil | 15 |
| Mentor del foro | `forum_helper` | media | 25 |
| Bitácora de notas | `grades_10` | media | 20 |
| Porrista | `supporter_5` | fácil | 15 |
| Creador de retos | `creator` | media | 20 |
| Primera victoria | `first_pass` | media | 25 |
| Excelencia académica | `high_average` | difícil | 50 |

## Pensum de Ingeniería de Software

**Fuente:** [`docs/pensum.png`](pensum.png). **Código:** `app/data/pensums.py`
(`SOFTWARE_ENGINEERING`).

- **Tamaño:** 9 semestres, 60 materias y **148 créditos**.
- **Códigos:** cada materia tiene un código `IS<semestre><nn>`, por ejemplo `IS101` para
  Introducción a la Ingeniería de Software.
- **Créditos:** la imagen del pensum **no indica créditos**. Los valores se asignaron como
  estimación (asignaturas técnicas y de ciencias = 3, formación humana = 1–2, inglés = 1,
  Práctica Empresarial = 6). Se pueden ajustar en `app/data/pensums.py`.

### Categorías

| Categoría | Criterio | Créditos |
|-----------|----------|----------|
| 🔬 Ciencias | Matemáticas, física, estadística, sistemas, investigación de operaciones | 35 |
| 📜 Humanidades | Formación humana (Ser, Saber…), investigación, emprendimiento, proyectos, ética, electivas | 23 |
| 💻 Tecnología | Programación, diseño, bases de datos, arquitectura, calidad, profundizaciones, práctica | 84 |
| 🌐 Idiomas | Inglés I a VI | 6 |

### Materias por semestre

| Sem. | Materias (créditos, categoría) | Créditos |
|------|--------------------------------|----------|
| 1 | Introducción a la Ingeniería de Software (3, T) · Innovación Tecnológica (2, T) · Teoría General de los Sistemas (2, C) · Fundamentos de Matemáticas (3, C) · Pensamiento Computacional (3, T) · Cátedra Pablo Olivares Marmolejo (1, H) · Inglés I (1, I) | 15 |
| 2 | Requerimientos de Software (3, T) · Programación I (3, T) · Metodologías de Software (2, T) · Cálculo Diferencial (3, C) · Álgebra Lineal (3, C) · Ser (Be-It) (1, H) · Inglés II (1, I) | 16 |
| 3 | Fundamentos de Diseño de Software (3, T) · Programación II (3, T) · Fundamentos de Bases de Datos (3, T) · Cálculo Integral (3, C) · Estadística I (3, C) · Saber Convivir (Live-It) (1, H) · Inglés III (1, I) | 17 |
| 4 | Diseño de Software (3, T) · Programación III (3, T) · Diseño de Bases de Datos (3, T) · Fundamentos de Investigación (2, H) · Estadística II (3, C) · Saber Hacer (Do-It) (1, H) · Inglés IV (1, I) | 16 |
| 5 | Arquitectura de Software (3, T) · Programación IV (3, T) · Teoría de Grafos (3, C) · Física I (3, C) · Saber Conocer (Know-It) (1, H) · Inglés V (1, I) | 14 |
| 6 | Pruebas de Software (3, T) · Proyecto de Software Empresarial (3, T) · Análisis Numérico (3, C) · Física II (3, C) · Espíritu Emprendedor (2, H) · Inglés VI (1, I) | 15 |
| 7 | Mantenimiento de Software (3, T) · Normatividad de Software (2, T) · Business Intelligence (3, T) · Profundización I (3, T) · Investigación Cualitativa y Cuantitativa (2, H) · Formulación y Evaluación de Proyectos de Ingeniería (2, H) · Electiva I (2, H) | 17 |
| 8 | Calidad del Software I (3, T) · Analítica y Visualización de Datos (3, T) · Profundización II (3, T) · Práctica Empresarial (6, T) · Ética, Constitución y Gobernanza (2, H) · Electiva II (2, H) | 19 |
| 9 | Calidad del Software II (3, T) · Experiencia de Usuario (3, T) · Tecnologías Emergentes (3, T) · Profundización III (3, T) · Investigación de Operaciones (3, C) · Gerencia de Proyectos de Ingeniería (2, H) · Electiva III (2, H) | 19 |

T = tecnología, C = ciencias, H = humanidades, I = idiomas.

### Agregar otro programa al catálogo

```python
# app/data/pensums.py
INDUSTRIAL = Pensum(
    program="Ingeniería Industrial",
    plan="Pensum Ingeniería Industrial",
    semesters=10,
    subjects=tuple(_semester(1, ("Cálculo Diferencial", 3, C), ...) + ...),
)
PENSUMS = {p.program: p for p in (SOFTWARE_ENGINEERING, INDUSTRIAL)}
```

El nuevo programa aparece automáticamente en el selector "Cargar pensum". Conviene usar un
prefijo de código distinto, adaptando `_semester`.

## Datos de demostración (`make seed-demo`)

`app/db/demo_data.py` → `load_demo()`:

- Es **idempotente**: si el primer usuario demo ya existe, no hace nada.
- Usa una semilla fija (`random.Random(7)`), así que los datos son reproducibles.
- Las cuentas demo se crean **ya activadas** (`require_verification=False`): no necesitan el
  enlace del correo.
- Todos los usuarios demo tienen la contraseña **`Demo1234`** y el correo
  `<usuario>@demo.edu.co`. Con Keycloak se crean también en el realm. Si ya existían en Keycloak
  (por ejemplo, tras `make reset-db`), sólo se crea la fila local, que se vincula en el primer
  login.

### Estudiantes y niveles

Todos cursan Ingeniería de Software con el pensum completo cargado:

| Usuario | Nombre | Semestre | Etapa | Perfil académico (nota media esperada) |
|---------|--------|----------|-------|----------------------------------------|
| `diego.lopez` | Diego López | 1 | Recién ingresa | 2,8: arranque difícil, **en riesgo**. |
| `valentina.rios` | Valentina Ríos | 1 | Recién ingresa | 4,1 |
| `carlos.ruiz` | Carlos Ruiz | 2 | Iniciando | 3,6 |
| `sofia.herrera` | Sofía Herrera | 3 | Iniciando | 4,3 |
| `laura.gomez` | Laura Gómez | 5 | Mitad de carrera | 3,9 |
| `mateo.castro` | Mateo Castro | 6 | Mitad de carrera | 3,3: varias materias repetidas. |
| `juan.perez` | Juan Pérez | 8 | A punto de terminar | 3,8 |
| `ana.martinez` | Ana Martínez | 9 | Último semestre | 4,4 |

### Cómo se genera la historia académica

1. Se carga el pensum completo con `academics.load_pensum`: 60 materias en estado `pendiente`.
2. **Semestres anteriores al actual:**
   - Cada materia recibe un docente y un plan de ítems al azar, por ejemplo
     *Parcial 1 30 % · Parcial 2 30 % · Examen final 40 %*.
   - Las notas siguen una distribución normal alrededor del nivel del estudiante, con −0,3 en
     las materias de ciencias.
   - El estado queda `aprobada` o `reprobada` según la nota.
   - Una materia **reprobada se repite** en el semestre siguiente. Si ese semestre ya pasó, se
     aprueba; si es el actual, queda `cursando`.
3. **Semestre actual:** las materias quedan `cursando` y sólo tienen una parte de sus ítems,
   como notas parciales.
4. **Semestres futuros:** las materias quedan `pendiente`.
5. Las fechas de entrega se distribuyen a lo largo de cada semestre: el actual empezó hace unos
   2 meses y cada semestre anterior dura unos 6 meses.

### Resto del contenido demo

| Tipo | Cantidad | Detalle |
|------|----------|---------|
| Publicaciones | 6 | Temas de la carrera (recursión, Cálculo Integral, inscripción, SQL, práctica empresarial, patrones de diseño). La primera está resuelta. |
| Comentarios | 2–3 por publicación | De otros estudiantes. |
| Seguimientos | 3 por estudiante | Al azar. |
| Mensajes de apoyo | 10 | Plantillas de ánimo. |
| Retos de la comunidad | 2 | "30 días de LeetCode" (de Diego, público, cierra en 30 días) y "Lee un artículo científico" (de Carlos, **sólo seguidores**). Cada uno con 4 participantes; un 60 % lo completa con evidencia. |
| Participaciones en retos globales | 5 por estudiante | Se completan con las **reglas reales** (`refresh_automatic`), así que son coherentes con los datos. |

### Regenerar los datos demo

```bash
make reset-db     # borra y recrea las tablas de la app (Keycloak no se toca)
make seed-demo
```
