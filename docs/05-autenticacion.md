# 5. Autenticación

El enunciado pide un *login básico*, opcionalmente con Keycloak. `app/auth/service.py`
implementa dos proveedores intercambiables con la variable `AUTH_PROVIDER`. Las vistas y el
resto de servicios no saben cuál está activo: siempre llaman a las mismas funciones públicas.

| Función pública | Descripción |
|-----------------|-------------|
| `begin_login(session, username, password) -> User \| None` | **Paso 1 del login:** verifica usuario y contraseña con el cliente `ct-ranking-pwcheck`, sin pedir OTP. Si la cuenta no tiene 2FA, completa el login y devuelve el usuario; si tiene 2FA, devuelve `None` y la UI pide el código. |
| `login(session, username, password, otp=None) -> User` | Login completo (paso 2 cuando hay 2FA): valida las credenciales y el código 2FA en `otp`, sincroniza el usuario local, actualiza `last_login` y verifica que la cuenta esté activa. Acepta usuario **o** correo. Lanza `EmailNotVerifiedError` si la cuenta no se activó. |
| `register(session, *, username, email, password, first_name, last_name, role=student, require_verification=True) -> User` | Valida los datos y verifica que el usuario y el correo sean únicos. Con Keycloak, la cuenta queda pendiente de activación y se envía el enlace al correo. |
| `resend_verification(login)` | Reenvía el enlace de activación. No revela si la cuenta existe. |
| `verify_credentials(user, password, otp=None)` | Re-autenticación para acciones sensibles (eliminar la cuenta, desactivar el 2FA). |
| `change_password(session, user, current, new, otp=None)` | Verifica la contraseña actual (y el código 2FA) y establece la nueva. |
| `validate_new_email(session, user, email)` | Valida el correo nuevo (formato, dominio, distinto del actual y libre). No cambia nada. |
| `apply_verified_email(session, user, email)` | Guarda un correo cuya posesión ya se comprobó y lo marca como verificado (en Keycloak, `emailVerified=true`). Sólo lo llama `accounts.confirm_email_change`, después de validar el código enviado a ese correo. |
| `change_names(session, user, first_name, last_name)` | Actualiza nombre y apellido. |
| `set_active(session, user, active)` | Habilita o deshabilita la cuenta. Lo usa el panel de administrador. |
| `google_login_enabled()`, `login_with_oidc(session, claims, *, allow_create=False) -> (User, creado)` | Google: si está habilitado, y el ingreso a partir de los *claims* OIDC de Keycloak. Valida el correo verificado y el dominio institucional (salvo que la cuenta existente sea de un admin). Busca la cuenta por `keycloak_id` y luego por correo; si ese correo ya está vinculado a **otro** usuario de Keycloak, rechaza el ingreso. Sin `allow_create` exige que la cuenta exista (`AccountNotFoundError`, y borra el usuario huérfano en Keycloak); con `allow_create` la crea. |
| `two_factor_supported()`, `two_factor_enabled(user)` | Indica si hay 2FA disponible (sólo con Keycloak) y si el usuario lo tiene activo. |
| `request_two_factor_setup(user)` | Pide a Keycloak que envíe el correo con el enlace para configurar el 2FA (QR). El enlace dura 12 horas. Como mucho un correo por minuto (igual que `resend_verification`). |
| `disable_two_factor(user, password, otp)` | Verifica la contraseña y el código, y borra las credenciales OTP en Keycloak. |

Todas lanzan `AuthError` con un mensaje en español apto para mostrar al usuario.

## Validaciones comunes

| Dato | Regla |
|------|-------|
| Usuario | `^[a-zA-Z0-9_.-]{3,30}$` y único, sin distinguir mayúsculas. |
| Correo | Formato `algo@dominio.tld`. Se guarda en minúsculas y debe ser único. Los **estudiantes** deben usar `@STUDENT_EMAIL_DOMAIN` (por defecto `@estudiantes.areandina.edu.co`): en el formulario sólo escriben la parte antes de la @ (`auth.student_email`), y `register`, `validate_new_email` y `login_with_oidc` lo validan (`validate_student_email`). Los administradores están exentos. |
| Nombre y apellido | Ambos obligatorios: Keycloak 26 los exige (ver abajo). |
| Contraseña | Mínimo 8 caracteres y máximo 72 bytes (límite de bcrypt). Debe contener letras y números. |

## Proveedor `keycloak` (por defecto)

### Configuración del realm

Keycloak importa el archivo `container/keycloak/ct-ranking-realm.json` en el primer arranque:

| Elemento | Configuración |
|----------|---------------|
| Realm | `ct-ranking`, `sslRequired: none` (desarrollo), `loginWithEmailAllowed: true`, `duplicateEmailsAllowed: false`, `bruteForceProtected: true`. |
| Roles de realm | `student`, `admin`. |
| Cliente `ct-ranking-app` | Confidencial (`client-secret` = `${KEYCLOAK_CLIENT_SECRET}`), `directAccessGrantsEnabled: true` (login con usuario y contraseña), `serviceAccountsEnabled: true`, `standardFlowEnabled: false`. |
| Cuenta de servicio del cliente | Roles de cliente `realm-management`: `manage-users`, `view-users`, `query-users`. |
| Usuario administrador | `${APP_ADMIN_USERNAME}` con correo y contraseña de `.env`, roles `admin` y `student`, correo verificado. |
| Flujo *direct grant* (por defecto en Keycloak) | Usuario → contraseña → **«Conditional OTP»**: si el usuario tiene 2FA, exige el código en el parámetro `otp`. |
| Flujo «direct grant - solo contraseña» y cliente `ct-ranking-pwcheck` | Copia del flujo sin el paso OTP, asociada a un cliente confidencial cuyos tokens duran 60 s. Sirve para el paso 1 del login: comprobar la contraseña antes de pedir el código 2FA. Como ese flujo no exige el OTP, su token queda **sin roles ni audiencia** (`fullScopeAllowed: false`, sólo el client scope `basic`): la API de cuenta de Keycloak y cualquier otro servicio lo rechazan. Lo crea `configure_keycloak.py`. |
| Protección contra fuerza bruta | Activa. Varios intentos fallidos seguidos bloquean temporalmente la cuenta. |

Lo que depende del entorno no está en el JSON, porque éste sólo se importa la primera vez. Lo
aplica `scripts/configure_keycloak.py` en cada `make up`:

- el servidor **SMTP** del realm (`KEYCLOAK_SMTP_*`, `MAIL_FROM`);
- los idiomas `es` y `en`, con español por defecto;
- `rootUrl`, `redirectUris` y `webOrigins` del cliente, con el valor de `APP_URL`. Así funciona
  «Volver a la aplicación» tras verificar el correo o configurar el 2FA.

### Flujo de login (Resource Owner Password Credentials)

```mermaid
sequenceDiagram
    participant U as Usuario
    participant L as ui/pages/login.py
    participant A as auth/service.py
    participant K as Keycloak
    participant DB as PostgreSQL (users)

    U->>L: usuario + contraseña
    L->>A: login(session, usuario, contraseña)
    A->>K: POST /realms/ct-ranking/protocol/openid-connect/token<br/>grant_type=password, client_id, client_secret
    alt credenciales inválidas (400/401)
        K-->>A: error
        A-->>L: AuthError("Usuario o contraseña incorrectos")
    else ok
        K-->>A: access_token (JWT)
        A->>A: decodifica el payload: sub, preferred_username,<br/>email, given_name, family_name, realm_access.roles
        A->>DB: busca el usuario por keycloak_id; si no, una cuenta<br/>sin vincular con el mismo correo verificado
        A->>DB: crea o actualiza: keycloak_id, email, nombres<br/>(role=admin sólo al crear, si el token trae "admin")
        A->>DB: last_login = now()
        A-->>L: User
        L->>L: session_state.user_id = user.id
    end
```

Detalles:

- **Firma del token.** El token se recibe directamente del endpoint de tokens de Keycloak por el
  canal backend (servidor a servidor), nunca desde el navegador, así que no se vuelve a verificar
  su firma: OpenID Connect Core (§3.1.3.7) permite confiar en el canal (TLS en producción) en ese
  caso. Sólo se decodifica el payload para leer los *claims*. La app tampoco guarda los tokens:
  la duración de la sesión la controla `SESSION_TTL_HOURS` (ver más abajo).
- **Vinculación de cuentas.** Nunca se vincula una fila local por username: con Google el
  username se deriva del correo y no prueba identidad. Si al crear la fila el username ya existe,
  se agrega un número (`carlos` → `carlos2`).
- **Primer login.** Si es la primera vez que el usuario entra y no tiene fila en `users` (por
  ejemplo, se creó a mano en la consola de Keycloak), la fila se crea automáticamente. Si existe
  una fila sin `keycloak_id` con el mismo correo verificado (como el admin que crea `init_db`),
  se vincula a ella.
- **Cuenta deshabilitada en Keycloak.** Keycloak responde `Account disabled` y la app lo
  traduce a "La cuenta está deshabilitada".

### Operaciones de administración (API Admin de Keycloak)

`KeycloakClient` primero obtiene un token de la cuenta de servicio
(`grant_type=client_credentials`) y lo guarda en caché hasta 30 s antes de que venza (si
Keycloak responde 401, lo renueva una vez). Las conexiones HTTP se reutilizan con un
`requests.Session`. Con ese token llama a:

| Operación | Endpoint | Cuándo |
|-----------|----------|--------|
| Crear usuario | `POST /admin/realms/ct-ranking/users` (con credencial no temporal) | `register` |
| Restablecer contraseña | `PUT /admin/realms/ct-ranking/users/{id}/reset-password` | `change_password` (después de verificar la contraseña actual con un login) |
| Actualizar usuario | `GET` + `PUT /admin/realms/ct-ranking/users/{id}` | `apply_verified_email`, `change_names`, `set_active` |
| Buscar usuario | `GET /admin/realms/ct-ranking/users?username=…&exact=true` (o `email=`) | Reenvío de la activación y diagnóstico de errores de login |
| Enviar enlace de activación | `PUT /admin/realms/ct-ranking/users/{id}/send-verify-email` | `register`, `resend_verification` |
| Enviar enlace de configuración de 2FA | `PUT /admin/realms/ct-ranking/users/{id}/execute-actions-email` con `["CONFIGURE_TOTP"]` | `request_two_factor_setup` |
| Listar o borrar credenciales OTP | `GET /users/{id}/credentials` y `DELETE /users/{id}/credentials/{credId}` | `two_factor_enabled`, `disable_two_factor` |
| Estado de fuerza bruta | `GET /admin/realms/ct-ranking/attack-detection/brute-force/users/{id}` | Mensaje «cuenta bloqueada temporalmente» |
| Borrar usuario | `DELETE /admin/realms/ct-ranking/users/{id}` | Purga de cuentas vencidas y registro que no pudo guardarse en la BD de la app (para no dejar un usuario huérfano) |

El `PUT` envía la representación **completa** del usuario, que se obtiene antes con el `GET`.
Con el *user profile* declarativo de Keycloak 24+, un `PUT` parcial puede borrar los
atributos que no se incluyen.

### ¿Por qué nombre y apellido son obligatorios?

Keycloak 26 activa por defecto un *user profile* que exige `firstName` y `lastName`. Si un
usuario no los tiene, Keycloak le asigna la acción requerida `VERIFY_PROFILE`, y el login por
contraseña falla con *"Account is not fully set up"*. Por eso:

- El formulario de registro pide nombre y apellido por separado.
- El modelo guarda `first_name` y `last_name`.
- Ambos se sincronizan con Keycloak.

### ¿Dónde están las contraseñas?

Con este proveedor **la base de datos de la app nunca guarda contraseñas**: `users.password_hash`
queda en `NULL`. Las credenciales viven en la base `keycloak`, cifradas con el algoritmo de hash
de Keycloak. Se gestionan desde la consola: http://localhost:8180 → realm `ct-ranking` → *Users*.

### Activación por correo y 2FA

- **Activación:** al registrarse, la cuenta se crea con `emailVerified=false` y la acción
  requerida `VERIFY_EMAIL`. Hasta abrir el enlace del correo, Keycloak responde
  *«Account is not fully set up»* (sólo si la contraseña es correcta) y la app lo traduce a
  `EmailNotVerifiedError`.
- **2FA:** la configuración (QR) y la validación del código las hace Keycloak.

Ver el detalle completo en
[Cuentas, seguridad y moderación](14-cuentas-seguridad-y-moderacion.md).

### Inicio de sesión con Google (OIDC)

Además del login por contraseña (*direct grant*), la app admite el flujo **Authorization Code**
de OpenID Connect con `st.login("google")`:

1. Keycloak recibe `kc_idp_hint=google` y redirige directo a Google.
2. Google sólo acepta cuentas del dominio institucional (`hostedDomain`).
3. Al volver, `auth.login_with_oidc`:
   - con «Crear cuenta con Google» (proveedor `googlesignup`), crea la cuenta si no existe;
   - con «Iniciar sesión con Google» (proveedor `google`), sólo entra si ya existe.

Con este método la sesión **persiste al recargar** la página, porque queda en una cookie firmada.
Ver [Inicio de sesión con Google](15-inicio-sesion-con-google.md).

## Proveedor `local`

Se activa con `AUTH_PROVIDER=local`. Lo usan las pruebas y sirve cuando no hay Keycloak.

| Operación | Implementación |
|-----------|----------------|
| Login | Busca el usuario por `username` o `email`, sin distinguir mayúsculas, y verifica con `bcrypt.checkpw` contra `users.password_hash`. |
| Registro | `bcrypt.hashpw(password, gensalt())` y se guarda en `password_hash`. |
| Cambio de contraseña | Verifica la actual con bcrypt y guarda el nuevo hash. |
| Correo, nombres, activar | Sólo actualizan la tabla `users`. El cambio de correo también exige el código enviado al correo nuevo. |
| Fuerza bruta | Tras 5 intentos fallidos con el mismo usuario, el login queda bloqueado 5 minutos (`app/core/ratelimit.py`, en memoria del proceso). |
| 2FA | No disponible: el TOTP lo gestiona Keycloak. |
| Administrador | `init_db` crea `APP_ADMIN_USERNAME` con el hash de `APP_ADMIN_PASSWORD` si aún no tiene contraseña. |

## Roles

- `users.role` vale `student` o `admin`. `User.is_admin` es la propiedad que consultan la UI y
  los servicios.
- **La app es la fuente de verdad del rol.** Un usuario se vuelve `admin` de tres maneras:
  - Un administrador lo promueve desde *Panel → Usuarios* (`admin.set_role`, que exige que quien
    lo hace sea admin y no permite cambiar el propio rol).
  - `init_db` siempre fuerza `role = admin` para `APP_ADMIN_USERNAME`.
  - Al crear la fila local de un usuario que sólo existía en Keycloak, se toma su rol de realm
    `admin` si lo tiene. Después ya no se sincroniza.
- Por eso degradar a alguien desde el panel **persiste** aunque conserve el rol `admin` en
  Keycloak, y quitarle el rol en Keycloak no cambia nada en la app.

## Sesión en la interfaz

- **Inicio de sesión exitoso:** `session.start_session` guarda `st.session_state["user_id"]` y
  la hora del login (`_login_at`).
- **En cada rerun:** `main.py` llama una vez a `session.current_user()`, que recarga el usuario
  desde la BD y lo deja en `_current_user` para que las páginas lo lean con `require_user()` sin
  otra consulta. Si ya no existe o fue deshabilitado, cierra la sesión (también la de Google).
- **Vencimiento:** una sesión iniciada con contraseña dura `SESSION_TTL_HOURS` horas (12 por
  defecto; `0` = sin límite). Al vencer, se cierra y se pide iniciar sesión de nuevo.
- **Cerrar sesión:** limpia todo `st.session_state` (y llama a `st.logout()` si se entró con
  Google).
- **Recargar el navegador:**
  - Con usuario y contraseña, crea una sesión nueva de Streamlit, así que hay que volver a
    iniciar sesión.
  - Con Google, la sesión **persiste**, porque `st.login` la guarda en una cookie firmada (ver
    [Inicio de sesión con Google](15-inicio-sesion-con-google.md)).
- **Entre los dos pasos del login con 2FA** la contraseña queda en `st.session_state` (memoria del
  servidor, nunca en el navegador) como máximo 5 minutos: es necesario porque Keycloak valida
  contraseña y código en la misma petición del flujo *direct grant*.
