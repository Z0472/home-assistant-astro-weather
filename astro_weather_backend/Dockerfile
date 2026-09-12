FROM alpine:edge

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

# ecCodes is reused for CHMI ALADIN and EUMETSAT MTG/FCI Cloud Mask GRIB-2.
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
COPY spatial_cloud_patch.py /app/spatial_cloud_patch.py
COPY spatial_timeline_patch.py /app/spatial_timeline_patch.py
COPY twilight_patch.py /app/twilight_patch.py
COPY edge_consistency_patch.py /app/edge_consistency_patch.py
COPY state_cache_patch.py /app/state_cache_patch.py
COPY entity_watchdog_patch.py /app/entity_watchdog_patch.py
COPY satellite_nowcast_patch.py /app/satellite_nowcast_patch.py
COPY storage_protection_patch.py /app/storage_protection_patch.py
COPY satellite_card_map_patch.py /app/satellite_card_map_patch.py
COPY satellite_lowload_patch.py /app/satellite_lowload_patch.py
COPY app.py /app/app.py
COPY cards /app/cards

CMD ["python3", "-u", "/app/app.py"]
