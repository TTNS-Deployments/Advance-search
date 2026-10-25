# Web app image for local and demo use (docker compose). Azure runs the app on App Service instead.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY Code/webapp/requirements.txt /tmp/webapp-requirements.txt
RUN pip install -r /tmp/webapp-requirements.txt

COPY Code/core /app/Code/core
RUN pip install -e "/app/Code/core[azure]"

COPY Code/webapp /app/Code/webapp
COPY Config /app/Config
COPY Data /app/Data

WORKDIR /app/Code/webapp
RUN ADVSEARCH_MODE=local DJANGO_DEBUG=false python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=1", "--threads=4", "--timeout=600", "config.wsgi"]
