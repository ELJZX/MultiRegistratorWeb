FROM python:3.12-slim-bookworm

ARG APP_VERSION=1.2.0
ARG GIT_REVISION=unknown
LABEL org.opencontainers.image.title="MultiRegistrator Web" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_REVISION}" \
      org.opencontainers.image.source="https://github.com/ELJZX/MultiRegistratorWeb"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build the WhiteNoise manifest so production containers do not need to run
# collectstatic at startup.
RUN mkdir -p /app/archive /app/staticfiles /app/logs \
    && DJANGO_DEBUG=0 python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "multiregistrator_web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
