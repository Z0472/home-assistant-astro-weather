# Astro Weather Backend 12.3.0

Home Assistant app/add-on for operational astrophotography weather decisions.

## Main Behavior

The backend publishes:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

The decision combines MET Norway, CHMI ALADIN, DWD ICON, internal Moon/astronomical-night calculation, CAMS/Open-Meteo AOD and 7Timer seeing. Version 12.3.0 additionally checks the spatial cloud neighbourhood around the observing site.

## Spatial Cloud Analysis

Enabled by default:

```yaml
spatial_cloud_analysis: true
spatial_radius_km: 30
```

Supported radius: **10–50 km**.

The backend creates a 17-point sampling pattern:

- centre,
- 8 compass directions at R/2,
- 8 compass directions at R.

DWD ICON cloud fields are requested for all points together. ALADIN reuses the already downloaded total-cloud GRIB and samples the same points locally. MET remains the centre point source in 12.3.0.

The spatial layer estimates:

- cloud range/stability around the site,
- nearby 50% cloud boundary,
- boundary distance and direction,
- incoming cloud or clearing trend,
- rough ETA of a significant change,
- dominant ICON cloud layer and pressure-level wind consistency.

This layer is conservative. It can turn an otherwise confident result into `NEJISTÉ`, but it does not override a hard veto and does not upgrade a bad forecast directly to `SPUSTIT`.

## Decision Safety

Hard vetoes remain precipitation, strong fog, excessive wind, Moon interference and configured bad AOD/seeing thresholds.

`Shoda modelů` is forecast-model agreement, not a calibrated probability of correctness. A cloud-only `NESPOUŠTĚT` can be softened to `NEJISTÉ` when model agreement is below 60% and no hard veto is present.

The hourly display covers sunset to sunrise. Good-block and operational decision calculations still use astronomical darkness only.

## Data Sources

- MET Norway Locationforecast: cloud cover/layers, fog, precipitation, temperature, dew point and wind.
- CHMI ALADIN open data: low/mid/high/total cloud cover; spatial analysis uses total cloud.
- DWD ICON Seamless via Open-Meteo: cloud layers, spatial neighbourhood and pressure-level wind consistency.
- Internal Moon calculation: astronomical night, phase, illumination, altitude and hourly interference.
- Open-Meteo Air Quality: CAMS AOD 550 and informational dust concentration.
- 7Timer ASTRO: seeing estimate.

SkyAccuracy.cz is not used.

## Default Quality Rules

AOD:

- up to `0.10`: no penalty,
- above `0.10`: gradual score penalty,
- from `0.30`: uncertainty,
- from `0.40`: bad hour.

Seeing:

- below `1.8"`: no penalty,
- from `1.8"`: lowers score / increases uncertainty,
- from `2.5"`: can remove an hour from a good block.

Moon:

- calculated internally,
- default interference starts at illumination >= `15 %` while the Moon is above the configured altitude threshold.

## Install / Update

Install from the Home Assistant App/Add-on Store repository:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

Set at least:

```yaml
latitude: 50.0755
longitude: 14.4378
altitude: 250
timezone: Europe/Prague
```

Use the real observing-site values, then start the app. `spatial_radius_km: 30` is the default and may be changed from 10 to 50 km.

## Dashboard

The app writes current card modules into `/config/www` and maintains the stable Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

Current entry modules:

```text
/config/www/astro-start-card-v26.js
/config/www/moon-forecast-card-v25.js
```

The main card intentionally presents only a short spatial message; detailed diagnostics stay in attributes/tooltips.

After an upgrade use `Ctrl+F5` if the browser still shows an older custom element.

## Development Checks

```bash
python3 -m py_compile astro_weather_backend/spatial_cloud_patch.py
python3 -m unittest -v tests/test_spatial_cloud_patch.py
python3 -m unittest -v tests/test_release_wiring.py
node --check astro_weather_backend/cards/astro-start-card-v26.js
```
