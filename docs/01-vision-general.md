# 1. Visión general

## Propósito

CT Ranking acompaña la vida académica de un estudiante universitario en un solo lugar:

- Ve su avance real en la carrera: plan de estudios, notas, promedios y créditos.
- Discute dudas y problemáticas con sus compañeros en foros.
- Participa en retos que lo motivan a mantener buenos hábitos (estudiar, registrar notas, ayudar
  a otros) y compite en un ranking.
- Construye una red de apoyo: sigue a sus compañeros y les envía mensajes de ánimo.

Los administradores tienen un panel para revisar la situación de un estudiante o de un grupo
y detectar a tiempo a quienes están en riesgo académico.

## Módulos funcionales

| Módulo | Página | Resumen |
|--------|--------|---------|
| Inicio | 🏠 Inicio | Tablero personal con promedios, puntos, posición en el ranking, retos en curso, últimas discusiones, apoyos recibidos y actividad de las personas que sigo. |
| Foros | 💬 Foros | Publicaciones con categoría, etiquetas y Markdown; comentarios, "me gusta" y estado resuelto. |
| Plan académico | 📚 Plan académico | Plan de estudios por semestres, materias con categoría y créditos, ítems calificables, promedios, gráficas de avance de créditos por categoría y de evolución del promedio, carga de pensum y botones para expandir o colapsar todos los menús. |
| Retos | 🏆 Retos | Retos globales con verificación automática y retos creados por estudiantes; ranking por reto y ranking general. |
| Personas | 👥 Personas | Búsqueda de estudiantes, seguir y dejar de seguir, perfil público y mensajes de apoyo. |
| Mensajes | 💌 Mensajes de apoyo | Bandeja de recibidos y enviados. |
| Perfil | 👤 Mi perfil | Datos personales y académicos, foto, correo y contraseña. |
| Administración | 🛡️ Panel de administrador | Métricas globales, detalle por estudiante, análisis de grupos, moderación y gestión de usuarios. |

La navegación está en el **menú lateral** izquierdo. Se puede ocultar, y estando oculto se
expande al pasar el mouse por el borde izquierdo de la ventana.

## Roles

| Rol | Valor en BD | Puede |
|-----|-------------|-------|
| Estudiante | `student` | Usar todos los módulos sobre su propia información, y crear retos de la comunidad. Sólo elimina su propio contenido. |
| Administrador | `admin` | Todo lo anterior y además: ver el panel de administrador, crear retos **globales** con verificación automática, ver todos los retos (incluidos los de "sólo seguidores"), eliminar cualquier publicación, comentario, reto o mensaje, cambiar roles y habilitar o deshabilitar cuentas. |

El rol `admin` llega por dos vías:

- El rol de realm `admin` en Keycloak.
- Una promoción desde el panel de administrador.

Ver [Autenticación](05-autenticacion.md#roles).

## Glosario

| Término | Significado en la plataforma |
|---------|------------------------------|
| **Pensum / plan de estudios** | Lista de materias de una carrera organizadas por semestre. El catálogo incluye Ingeniería de Software (9 semestres, 60 materias, 148 créditos). |
| **Materia** (`Subject`) | Una asignatura en el plan de un estudiante. Tiene semestre, créditos, categoría y estado. |
| **Estado de materia** | `pendiente` (planeada), `cursando`, `aprobada`, `reprobada`. |
| **Categoría de materia** | `ciencias`, `humanidades`, `tecnologia`, `idiomas`. Agrupa el avance de créditos. |
| **Ítem calificable** (`GradeItem`) | Un trabajo, tarea, quiz o parcial con nombre, descripción, nota y porcentaje opcional. |
| **Nota de la materia** | Promedio (ponderado o simple) de sus ítems. Ver [reglas](10-reglas-de-negocio.md#nota-de-una-materia). |
| **Promedio del semestre** | Promedio de las notas de las materias de un semestre, ponderado por créditos. |
| **Promedio general** | Promedio acumulado de todas las materias vistas, ponderado por créditos. |
| **Reto global** | Reto igual para todos los estudiantes, verificado automáticamente por una regla. |
| **Reto de la comunidad** | Reto creado por un estudiante; se completa aportando evidencia. |
| **Regla** | Código (`first_post`, `grades_10`…) que mide automáticamente el progreso del usuario. |
| **Ranking / leaderboard** | Orden de usuarios por puntos de retos completados, con bonus para quien termina primero. |
| **Estudiante en riesgo** | Estudiante cuyo promedio general o del semestre actual es menor que la nota mínima aprobatoria. |
| **Mensaje de apoyo** | Mensaje corto de ánimo enviado a otro usuario. |
