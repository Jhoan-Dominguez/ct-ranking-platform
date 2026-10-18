# CT Ranking

Plataforma académica y social para estudiantes, construida con Streamlit, PostgreSQL y Keycloak.
Incluye:
- Foros de discusión.
- Plan de estudios con notas y promedios.
- Retos dinámicos con ranking.
- Seguidores y mensajes de apoyo.
- Panel de administrador.

```bash
make create && make up && make seed-demo && make run
```

- App: http://localhost:8501. Entra como `admin` / `Admin123!` o con un usuario demo, por
  ejemplo `ana.martinez` (último semestre) o `diego.lopez` (primer semestre), con la contraseña
  `Demo1234`.
- Keycloak: http://localhost:8180 (`admin` / `admin`).

- Documentación técnica completa: [`docs/`](docs/README.md).
- Resumen de lo construido y de lo agregado al enunciado: [PROYECTO.md](PROYECTO.md).
