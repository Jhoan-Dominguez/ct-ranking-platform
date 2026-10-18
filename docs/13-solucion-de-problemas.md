# 13. Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `make up` falla con *Bind for 0.0.0.0:8180 failed: port is already allocated* (o 5432) | Otro proceso o contenedor usa el puerto. | Cambia `KEYCLOAK_PORT` **y** `KEYCLOAK_URL`, o `POSTGRES_PORT`, en `.env` y repite `make up`. Para ver quién lo usa: `docker ps --format '{{.Names}} {{.Ports}}'` o `ss -ltn`. |
| `wait_for_services.py` termina con "Keycloak no respondió en 180s" | Primer arranque lento, falta de memoria o error al importar el realm. | `make logs`. Busca errores de import del realm o de conexión a PostgreSQL. En equipos lentos vuelve a ejecutar `make up`. |
| La app muestra "No hay conexión con la base de datos" | Los contenedores no están levantados. | `make up` (o `make ps` para verificar su estado). |
| Login: "No fue posible contactar el servidor de autenticación (Keycloak)" | Keycloak no está arriba o `KEYCLOAK_URL` es incorrecta. | `make ps`; `curl $KEYCLOAK_URL/realms/ct-ranking`. |
| Login: "Usuario o contraseña incorrectos" con `admin` | Se confundió la contraseña de la consola de Keycloak (`admin`/`admin`) con la de la plataforma (`admin`/`Admin123!`). | Usa `Admin123!` en http://localhost:8501. Los intentos fallidos aparecen en `make logs` como `LOGIN_ERROR … invalid_user_credentials`. |
| Cambié `APP_ADMIN_PASSWORD` en `.env` y no funciona | El realm sólo se importa cuando el volumen está vacío. | Cambia la contraseña en la consola de Keycloak o desde **Mi perfil**. Para reimportar todo: `make destroy && make up` (borra los datos). |
| Login: "Account is not fully set up" (en `make logs`) | El usuario de Keycloak no tiene nombre o apellido, por ejemplo porque se creó a mano en la consola. | Complétalos en la consola de Keycloak (*Users → usuario → Details*). |
| Login: "La cuenta está deshabilitada" | Un administrador la deshabilitó. | *Panel → Usuarios → Habilitar cuenta*, o actívala en la consola de Keycloak. |
| El usuario demo existe en Keycloak pero no en la app tras `make reset-db` | `reset-db` borra sólo la BD de la app. | `make seed-demo` recrea las filas locales, que se vinculan en el primer login. |
| `sqlalchemy … column "category" does not exist` (u otra columna) | Se actualizó el código con columnas nuevas y no hay migraciones. | `make reset-db && make seed-demo` (pierde los datos de la app), o agrega la columna con `ALTER TABLE`. |
| Al recargar el navegador se cierra la sesión | La sesión vive en `st.session_state`, que es por conexión. | Es el comportamiento esperado. Vuelve a iniciar sesión. |
| La foto de perfil no se sube | Supera 5 MB o no es una imagen válida. | Usa png, jpg o webp de menos de 5 MB. |
| "La suma de porcentajes de la materia superaría el 100%" | Los ítems ya suman cerca de 100 %. | Ajusta los porcentajes existentes o deja el nuevo ítem en 0 % (promedio simple). |
| No veo un reto de un compañero | El reto es "sólo seguidores". | Sigue al creador desde **Personas**. |
| No puedo unirme a un reto | El reto está cerrado (inactivo o fuera de fechas). | Pide al creador que lo reabra o que ajuste las fechas. |
| El menú lateral oculto no se abre al pasar el mouse | Pantalla táctil o navegador que no reporta un puntero con hover (el script sólo se activa con mouse). También puede pasar tras actualizar Streamlit, si cambiaron los `data-testid` de los botones del menú. | Usa el botón «>>». Tras una actualización de Streamlit, revisa los selectores en `app/ui/sidebar_hover.js` (ver [Páginas y vistas](09-paginas-y-vistas.md#menú-lateral-expandir-al-pasar-el-mouse)). |
| «Expandir todo» no abre una materia recién creada | La materia aún no existía cuando se pulsó el botón. | Pulsa de nuevo «Expandir todo». El estado se guarda por materia. |
| `pre-commit run --all-files` no revisa mis archivos nuevos | Sólo revisa los archivos versionados. | `git add` primero, o `pre-commit run --files <rutas>`. |
| No llegan los correos (activación, 2FA, código de eliminación) | Mailpit no está levantado, el SMTP no está configurado en Keycloak o falla el SMTP real. | En desarrollo abre http://localhost:8025. Ejecuta `make up`, que reconfigura el SMTP de Keycloak. Con un SMTP real, revisa `SMTP_*` y `KEYCLOAK_SMTP_*`. |
| «No fue posible enviar el correo…» | La app no pudo conectarse al SMTP (`SMTP_HOST:SMTP_PORT`). | `make ps` (contenedor `mailpit`) o revisa las credenciales del SMTP real. |
| «Tu cuenta aún no está activada» | No se abrió el enlace de verificación. | Abre el correo «Verificación de email» o usa **Reenviar correo de activación**. |
| El enlace de activación o de 2FA dice que expiró | El enlace tiene vigencia limitada (el de 2FA dura 12 horas). | Pide uno nuevo desde la app. |
| «Usuario, contraseña o código de verificación incorrectos» con la contraseña correcta | La cuenta tiene 2FA y falta el código, o el código expiró o ya se usó. | Escribe el código actual de la app autenticadora. Si acabas de usarlo, espera al siguiente. |
| «Demasiados intentos fallidos…» | Protección contra fuerza bruta de Keycloak. | Espera un minuto. Un admin puede desbloquear en la consola de Keycloak (*Users → usuario*). |
| Perdí el celular con el 2FA | La credencial OTP sigue activa. | Un admin la elimina en la consola de Keycloak (*Users → usuario → Credentials → OTP → Delete*). |
| La cuenta no se borró al pasar los 7 días | La app no estaba en ejecución, y el hilo de purga sólo corre mientras lo está. | `make purge-accounts`, o prográmalo con cron. |
| Aviso `missing ScriptRunContext` al ejecutar scripts o pruebas | Se importó Streamlit fuera de `streamlit run` (por ejemplo, con `AppTest`). | Se puede ignorar. |

## Comandos de diagnóstico

```bash
make ps                                            # estado de los contenedores
make logs                                          # logs de PostgreSQL y Keycloak
docker compose exec db psql -U ctranking -d ctranking -c '\dt'      # tablas de la app
docker compose exec db psql -U ctranking -d ctranking \
  -c "select username, role, is_active, keycloak_id is not null as kc from users;"
curl -s localhost:8180/realms/ct-ranking/.well-known/openid-configuration | head -c 200
curl -s localhost:8501/_stcore/health
```
