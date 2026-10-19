# Imagen de la app (Streamlit) para Docker. La versión para Podman es container/podman/Containerfile
# (mismo contenido; mantenerlos iguales). El contexto de compilación es la raíz del repositorio y
# .dockerignore deja fuera .env, .venv, etc.
#
#   docker build -f container/docker/Dockerfile -t localhost/ct-ranking-app .
#
# Nombre completo de la imagen base (docker.io/...): funciona igual en Docker y en Podman.
FROM docker.io/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Usuario sin privilegios. El código queda de root (sólo lectura para la app).
RUN useradd --create-home --uid 10001 app

WORKDIR /app

# Dependencias primero: esta capa se reutiliza mientras requirements.txt no cambie.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
COPY .streamlit/config.toml .streamlit/config.toml

# secrets.toml (st.login) se genera al arrancar en el HOME del usuario, que Streamlit también lee
# (~/.streamlit/secrets.toml). En compose ese directorio es un volumen: el secreto de la cookie
# sobrevive a los reinicios. Se crea aquí para que el volumen herede el dueño.
RUN mkdir -p /home/app/.streamlit && chown app:app /home/app/.streamlit

USER app

ENV STREAMLIT_SECRETS_FILE=/home/app/.streamlit/secrets.toml \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

EXPOSE 8501

# Sin ENTRYPOINT: `compose run --rm app python -m ...` reemplaza este comando.
CMD ["sh", "-c", "python -m scripts.write_streamlit_secrets && exec streamlit run app/main.py"]
