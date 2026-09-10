FROM alpine:edge

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

# Používáme jen CLI nástroj grib_get z ecCodes, ne Python bindings.
# Tím obejdeme nekompatibilitu Python wheelu eccodeslib v HA Core.
RUN echo "https://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories \
    && apk add --no-cache \
       python3 \
       py3-websocket-client \
       ca-certificates \
       tzdata \
       eccodes

WORKDIR /app
COPY astro_weather_backend.py /app/astro_weather_backend.py
COPY cards /app/cards

CMD ["python3", "-u", "/app/astro_weather_backend.py"]
