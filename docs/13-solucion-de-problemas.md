# 13. Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `make up` falla con *Bind for 127.0.0.1:8180 failed: port is already allocated* (o 5432) | Otro proceso o contenedor usa el puerto. | Cambia `KEYCLOAK_PORT` **y** `KEYCLOAK_PUBLIC_URL`, `POSTGRES_PORT` o `APP_PORT` (**y** `APP_URL`) en `.env` y repite `make up`. Para ver quién lo usa: `docker ps --format '{{.Names}} {{.Ports}}'` (o `podman ps`) o `ss -ltn`. |
| `wait_for_services.py` termina con "Keycloak no respondió en 180s" | Primer arranque lento, falta de memoria o error al importar el realm. | `make logs`. Busca errores de import del realm o de conexión a PostgreSQL. En equipos lentos vuelve a ejecutar `make up`. |
| La app muestra "No hay conexión con la base de datos" | Los contenedores no están levantados. | `make up` (o `make ps` para verificar su estado). |
| Login: "No fue posible contactar el servidor de autenticación (Keycloak)" | Keycloak no está arriba. | `make ps`; `curl localhost:8180/realms/ct-ranking`. |
| Login: "Usuario o contraseña incorrectos" con `admin` | Se confundió la contraseña de la consola de Keycloak (`admin`/`admin`) con la de la plataforma (`admin`/`Admin123!`). | Usa `Admin123!` en http://localhost:8501. Los intentos fallidos aparecen en `make logs` como `LOGIN_ERROR … invalid_user_credentials`. |
| Cambié `APP_ADMIN_PASSWORD` en `.env` y no funciona | El realm sólo se importa cuando el volumen está vacío. | Cambia la contraseña en la consola de Keycloak o desde **Mi perfil**. Para reimportar todo: `make destroy && make up` (borra los datos). |
| Login: "Account is not fully set up" (en `make logs`) | El usuario de Keycloak no tiene nombre o apellido, por ejemplo porque se creó a mano en la consola. | Complétalos en la consola de Keycloak (*Users → usuario → Details*). |
| Login: "La cuenta está deshabilitada" | Un administrador la deshabilitó. | *Panel → Usuarios → Habilitar cuenta*, o actívala en la consola de Keycloak. |
| El usuario demo existe en Keycloak pero no en la app tras `make reset-db` | `reset-db` borra sólo la BD de la app. | `make seed-demo` recrea las filas locales, que se vinculan en el primer login. |
| `sqlalchemy … column "category" does not exist` (u otra columna) | Se actualizó el código con columnas nuevas y no hay migraciones. | `make reset-db && make seed-demo` (pierde los datos de la app), o agrega la columna con `ALTER TABLE`. |
| Al recargar el navegador se cierra la sesión | Con usuario y contraseña, la sesión vive en `st.session_state`, que es por conexión. | Es el comportamiento esperado. Vuelve a iniciar sesión. Con Google la sesión sí persiste (cookie de `st.login`). |
| «Tu sesión venció. Inicia sesión de nuevo.» | Pasaron más de `SESSION_TTL_HOURS` horas (12 por defecto) desde el login con contraseña. | Inicia sesión otra vez, o ajusta `SESSION_TTL_HOURS` en `.env` (`0` = sin límite). |
| «Ya te enviamos un código hace un momento» / «Espera un minuto» | Entre dos correos con código o enlace debe pasar un minuto. | Espera y vuelve a pedirlo. |
| `init_db` falla al crear `uq_users_alias_lower` | Hay dos usuarios con el mismo alias sin distinguir mayúsculas (datos anteriores a la restricción). | Cambia uno de los alias (`UPDATE users SET alias = '' WHERE id = …`) y repite `make init-db`. |
| La foto de perfil no se sube | Supera 5 MB o no es una imagen válida. | Usa png, jpg o webp de menos de 5 MB. |
| "La suma de porcentajes de la materia superaría el 100%" | Los ítems ya suman cerca de 100 %. | Ajusta los porcentajes existentes o deja el nuevo ítem en 0 % (promedio simple). |
| No veo un reto de un compañero | El reto es "sólo seguidores". | Sigue al creador desde **Personas**. |
| No puedo unirme a un reto | El reto está cerrado (inactivo o fuera de fechas). | Pide al creador que lo reabra o que ajuste las fechas. |
| El menú lateral oculto no se abre al pasar el mouse | Pantalla táctil o navegador que no reporta un puntero con hover (el script sólo se activa con mouse). También puede pasar tras actualizar Streamlit, si cambiaron los `data-testid` de los botones del menú. | Usa el botón «>>». Tras una actualización de Streamlit, revisa los selectores en `app/ui/assets/sidebar_hover.js` (ver [Páginas y vistas](09-paginas-y-vistas.md#menú-lateral-expandir-al-pasar-el-mouse)). |
| «Expandir todo» no abre una materia recién creada | La materia aún no existía cuando se pulsó el botón. | Pulsa de nuevo «Expandir todo». El estado se guarda por materia. |
| `pre-commit run --all-files` no revisa mis archivos nuevos | Sólo revisa los archivos versionados. | `git add` primero, o `pre-commit run --files <rutas>`. |
| No llegan los correos (activación, 2FA, código de eliminación) | Mailpit no está levantado, el SMTP no está configurado en Keycloak o falla el SMTP real. | En desarrollo abre http://localhost:8025. Ejecuta `make up`, que reconfigura el SMTP de Keycloak. Con un SMTP real, revisa `SMTP_*` y `KEYCLOAK_SMTP_*`. |
| «No fue posible enviar el correo…» | La app no pudo conectarse al SMTP (`SMTP_HOST:SMTP_PORT`). Con un `.env` antiguo, `SMTP_HOST=localhost` apunta al propio contenedor de la app. | Usa `SMTP_HOST=mailpit` (o tu SMTP real) y `make run`. `make ps` (contenedor `mailpit`) o revisa las credenciales del SMTP real. |
| «Tu cuenta aún no está activada» | No se abrió el enlace de verificación. | Abre el correo «Verificación de email» o usa **Reenviar correo de activación**. |
| El enlace de activación o de 2FA dice que expiró | El enlace tiene vigencia limitada (el de 2FA dura 12 horas). | Pide uno nuevo desde la app. |
| «El código no es correcto o ya venció» (paso 2 del login) | El código de la app autenticadora expiró o ya se usó, o el reloj del celular está desfasado. | Escribe el código actual. Si acabas de usarlo, espera al siguiente. Revisa que la hora del celular sea automática. |
| «Demasiados intentos fallidos…» | Protección contra fuerza bruta de Keycloak. | Espera un minuto. Un admin puede desbloquear en la consola de Keycloak (*Users → usuario*). |
| Perdí el celular con el 2FA | La credencial OTP sigue activa. | Un admin la elimina en la consola de Keycloak (*Users → usuario → Credentials → OTP → Delete*). |
| La cuenta no se borró al pasar los 7 días | La app no estaba en ejecución, y el hilo de purga sólo corre mientras lo está. | `make purge-accounts`, o prográmalo con cron. |
| No aparecen los botones de Google | `GOOGLE_CLIENT_ID` está vacío o no se ejecutó `make up` después de cambiar `.env`. | Configura las credenciales ([guía](15-inicio-sesion-con-google.md)) y ejecuta `make up`. |
| «No existe una cuenta en CT Ranking para …» al usar Google | Se usó «Iniciar sesión con Google» sin tener cuenta. | Pulsa **Crear cuenta con Google** (o usa la pestaña *Crear cuenta*). |
| Error al pulsar un botón de Google tras cambiar `.env` | La app en ejecución todavía tiene la configuración anterior de `st.login`. | `make run`: recrea el contenedor de la app, que regenera `secrets.toml` al arrancar. |
| Tras volver de Google: error de *issuer* o de token | `KEYCLOAK_PUBLIC_URL` no coincide con la URL con la que el navegador abre Keycloak. | Ajusta `KEYCLOAK_PUBLIC_URL` (y `KEYCLOAK_PORT`) en `.env` y repite `make up`. |
| `make up` con Podman: *short-name … did not resolve* | Imagen sin nombre completo. | Las de `container/podman/compose.yaml` ya lo tienen; si agregas una, usa `docker.io/...`. |
| Con Podman en Fedora/RHEL: *Permission denied* al leer `/docker-entrypoint-initdb.d` o el realm | SELinux bloquea la carpeta montada. | Los montajes llevan `z`; si agregas uno, añade `:z`. |
| `podman compose`: *looking up compose provider failed* | No hay provider de compose instalado. | Instala `podman-compose` ≥ 1.1 (ver [`container/README.md`](../container/README.md#probar-con-podman)). |
| Con Podman, Keycloak se reinicia una o dos veces al arrancar | Arrancó antes que PostgreSQL (la versión de Podman no espera al healthcheck). | Normal: se recupera solo y `setup` espera a que esté listo. |
| Al pasar de Docker a Podman la base de datos está vacía | Cada motor tiene sus propios volúmenes. | Respalda con un motor y restaura con el otro ([Despliegue](03-despliegue-y-operacion.md#respaldo-y-restauración)). |
| Cambié código y la app no lo refleja | La app corre desde la imagen. | `make run` (reconstruye) o trabaja con `make dev` (monta el código y recarga al guardar). |
| Google muestra `redirect_uri_mismatch` | La URI registrada en Google Cloud no coincide con la del *broker* de Keycloak. | Registra `<KEYCLOAK_URL>/realms/ct-ranking/broker/google/endpoint` en el cliente OAuth. |
| «Debes usar tu correo institucional…» tras volver de Google | Se eligió una cuenta que no es `@estudiantes.areandina.edu.co`. | Pulsa «Usar otra cuenta de Google» y elige la cuenta institucional. |
| Keycloak pide «vincular cuenta» la primera vez con Google | Ya existía una cuenta con ese correo, registrada con el formulario. | Confirma con la contraseña de esa cuenta (o con el enlace por correo). Queda vinculada. |
| `make up` falla con `env file … .env not found` | No existe `.env`. | `make env` (lo crea desde `.env.example`). |
| Aviso `missing ScriptRunContext` al ejecutar scripts o pruebas | Se importó Streamlit fuera de `streamlit run` (por ejemplo, con `AppTest`). | Se puede ignorar. |

## Comandos de diagnóstico

```bash
make ps                                            # estado de los contenedores
make logs                                          # logs de todos los contenedores
make shell                                         # bash dentro de la imagen de la app
COMPOSE="docker compose -p ct-ranking --env-file .env -f container/docker/compose.yaml"   # o podman/
$COMPOSE exec db psql -U ctranking -d ctranking -c '\dt'      # tablas de la app
$COMPOSE exec db psql -U ctranking -d ctranking \
  -c "select username, role, is_active, keycloak_id is not null as kc from users;"
curl -s localhost:8180/realms/ct-ranking/.well-known/openid-configuration | head -c 200
curl -s localhost:8501/_stcore/health
```
