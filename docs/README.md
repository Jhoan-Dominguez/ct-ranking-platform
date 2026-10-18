# Documentación de CT Ranking

CT Ranking es una plataforma académica y social para estudiantes universitarios, construida con
**Streamlit**, **PostgreSQL** y **Keycloak**. Esta carpeta reúne toda la documentación técnica y
funcional del proyecto.

## Índice

| # | Documento | Contenido |
|---|-----------|-----------|
| 1 | [Visión general](01-vision-general.md) | Propósito, módulos funcionales, roles y glosario. |
| 2 | [Requisitos e instalación](02-requisitos-e-instalacion.md) | Software necesario, instalación paso a paso y variables de entorno. |
| 3 | [Despliegue y operación](03-despliegue-y-operacion.md) | Servicios Docker, comandos `make`, puertos, respaldos y recomendaciones para producción. |
| 4 | [Arquitectura](04-arquitectura.md) | Tecnologías, capas, estructura de carpetas y flujo de una petición. |
| 5 | [Autenticación](05-autenticacion.md) | Keycloak y proveedor local: login, registro, cambio de contraseña, roles. |
| 6 | [Modelo de datos](06-modelo-de-datos.md) | Diagrama entidad-relación, cada tabla con sus columnas, índices y restricciones. |
| 7 | [Persistencia y acceso a la base de datos](07-persistencia.md) | Cómo la app se conecta, transacciones, qué se guarda y dónde. |
| 8 | [Servicios](08-servicios.md) | Capa de lógica de negocio: cada módulo y sus funciones. |
| 9 | [Páginas y vistas](09-paginas-y-vistas.md) | Qué hace cada página de la interfaz y qué servicios y tablas usa. |
| 10 | [Reglas de negocio y cálculos](10-reglas-de-negocio.md) | Promedios, avance de créditos, retos, ranking y estudiantes en riesgo. |
| 11 | [Datos iniciales, pensum y demo](11-datos-iniciales-y-demo.md) | Retos globales, pensum de Ingeniería de Software y datos de demostración. |
| 12 | [Desarrollo, calidad y pruebas](12-desarrollo-y-pruebas.md) | Flujo de trabajo, pre-commit (isort y ruff), pruebas y cómo extender la plataforma. |
| 13 | [Solución de problemas](13-solucion-de-problemas.md) | Errores frecuentes y cómo resolverlos. |
| 14 | [Cuentas, seguridad y moderación](14-cuentas-seguridad-y-moderacion.md) | Activación por correo, 2FA con QR, eliminación diferida, bloqueos, reportes y correo (Mailpit/SMTP). |

## Inicio rápido

```bash
make create      # .env + dependencias en .venv + hooks de pre-commit
make up          # PostgreSQL + Keycloak + Mailpit en Docker; configura Keycloak, crea tablas y datos base
make seed-demo   # usuarios y datos de ejemplo (opcional)
make run         # http://localhost:8501
```

- Administrador: `admin` / `Admin123!`.
- Correos de desarrollo (Mailpit): http://localhost:8025.
- Usuarios demo: ver [Datos iniciales y demo](11-datos-iniciales-y-demo.md), contraseña `Demo1234`.

## Otros documentos del repositorio

- [`../README.md`](../README.md): resumen corto del proyecto.
- [`../PROYECTO.md`](../PROYECTO.md): qué se hizo y qué se agregó respecto al enunciado original.
- [`../project.md`](../project.md): enunciado original del proyecto.
- [`pensum.png`](pensum.png): plan de estudios de Ingeniería de Software usado en el catálogo.
