FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PGSSLMODE=verify-full PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libeccodes-tools ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 astro && useradd --uid 10001 --gid astro --no-create-home astro
WORKDIR /app
COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud/requirements.txt
COPY astro_weather_backend/ /app/astro_weather_backend/
COPY cloud/ /app/cloud/
RUN mkdir -p /data/cache && chown -R astro:astro /data
USER 10001:10001
EXPOSE 8099
CMD ["python", "/app/cloud/server.py", "serve"]
