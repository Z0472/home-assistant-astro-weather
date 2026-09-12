FROM alpine:edge

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

# Používáme CLI nástroje ecCodes (grib_get + grib_ls), ne Python bindings.
# grib_get čte ALADIN a grib_ls ověřuje, že lokalita leží u nativní sítě modelu.
RUN echo "https://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories \
    && apk add --no-cache \
       python3 \
       py3-websocket-client \
       ca-certificates \
       tzdata \
       eccodes

WORKDIR /app
COPY astro_weather_backend.py /app/astro_weather_backend.py
COPY weather_models.py /app/weather_models.py
COPY cloud_consensus.py /app/cloud_consensus.py
COPY model_runtime.py /app/model_runtime.py
COPY confidence_patch.py /app/confidence_patch.py
COPY night_forecast_patch.py /app/night_forecast_patch.py
COPY app.py /app/app.py
COPY cards /app/cards

CMD ["python3", "-u", "/app/app.py"]
