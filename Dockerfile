FROM python:3.12-slim

ARG APP_VERSION=1.1.0
LABEL org.opencontainers.image.title="MultiRegistrator Web" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/archive /app/staticfiles /app/logs \
    && python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "multiregistrator_web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
