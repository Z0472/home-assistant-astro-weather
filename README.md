# Home Assistant Astro Weather

Home Assistant app/add-on for astrophotography planning. It combines MET Norway, CHMU ALADIN, internal Moon/night calculation, CAMS AOD 550 through Open-Meteo, and 7Timer seeing into one practical decision: **SPUSTIT / NEJISTE / NESPOUSTET**.

## Current Version

**Astro Weather Backend 12.1.4**

This version is designed for a clean Home Assistant install:

- no external Moon integration,
- no `moon_photo_forecast.py`,
- no `moon_forecast.yaml`,
- no `astro_weather_backend.yaml` REST package,
- no `numpy`, `skyfield`, or `de440.bsp`,
- no SkyAccuracy dependency,
- dashboard card files are installed by the add-on.

The backend app publishes these Home Assistant entities itself through the Supervisor API:

- `sensor.astro_weather_detail`
- `sensor.astro_vhodnost_foceni`
- `sensor.mesic_foceni_predpoved`

The Moon entity is now a compatibility output for existing dashboard cards, not an input dependency.

The default MET User-Agent is generic and points to this repository, and the bundled location is only a sample default. Set your real latitude, longitude and altitude in the Home Assistant app configuration after install.

## Automatic Install From GitHub

The normal install path is the Home Assistant App/Add-on Store repository flow. No files from this repository need to be copied into `/addons`.

In Home Assistant open **Settings -> Apps -> Install app -> three-dot menu -> Repositories** and add:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

Then install **Astro Weather Backend** from the store.

Future upgrades are handled by Home Assistant through **Check for updates** or **Auto update**. A new release only needs a higher version in `astro_weather_backend/config.yaml`.

Important: Home Assistant Supervisor must be able to read this repository directly. If the repository is private, make it public or publish the add-on in a public release repository before installing from Store.

The repository contains the required root `repository.yaml` and the add-on directory `astro_weather_backend/`.

## Data Sources

- MET Norway Locationforecast: clouds, cloud layers, fog, precipitation, temperature, dew point, wind.
- CHMU ALADIN open data: low/mid/high/total cloud cover.
- Internal Moon calculation: astronomical night, Moon phase, illumination, altitude, hourly interference.
- Open-Meteo Air Quality API: CAMS AOD 550 and dust as surface concentration in `ug/m3`.
- 7Timer ASTRO JSON API: seeing and transparency index.

SkyAccuracy.cz is no longer used. If Open-Meteo/CAMS or 7Timer is unavailable, stale, or changes shape, AOD/seeing are ignored and the decision continues from MET + ALADIN + internal Moon.

## Dashboard Cards

The add-on installs current dashboard card files to `/config/www` on startup:

- `/config/www/astro-start-card.js`
- `/config/www/moon-forecast-card.js`

Keep these Lovelace resources configured in Home Assistant:

```text
/local/astro-start-card.js?v=17
/local/moon-forecast-card.js?v=19
```

The source TXT copies remain in [cards/](cards/) for manual inspection or emergency use.

## Tests

Run from repository root:

```bash
python3 -m py_compile astro_weather_backend/astro_weather_backend.py
python3 -m unittest -v tests/test_astro_weather_backend.py
```
