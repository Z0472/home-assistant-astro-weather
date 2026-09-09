# Home Assistant Astro Weather

Home Assistant app/add-on for astrophotography planning. It combines MET Norway, CHMU ALADIN, internal Moon/night calculation, CAMS/Open-Meteo AOD 550, Open-Meteo dust concentration and 7Timer seeing into one practical decision: **SPUSTIT / NEJISTE / NESPOUSTET**.

## Repository Description

Suggested GitHub **About -> Description** text:

```text
Home Assistant add-on for astrophotography weather decisions using MET Norway, CHMU ALADIN, internal Moon, CAMS/Open-Meteo AOD and 7Timer seeing.
```

Suggested GitHub topics:

```text
home-assistant, addon, astronomy, astrophotography, weather, aladin, cams, moon, seeing, 7timer
```

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

1. In Home Assistant open **Settings -> Apps -> Install app**.
2. Open the three-dot menu and choose **Repositories**.
3. Add this repository URL:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

4. Install **Astro Weather Backend** from the store.
5. Open the add-on configuration and set at least `latitude`, `longitude`, `altitude` and `timezone`.
6. Start the add-on.
7. Optionally enable **Start on boot**, **Watchdog** and **Auto update**.

Future upgrades are handled by Home Assistant through **Check for updates** or **Auto update**. A new release only needs a higher version in `astro_weather_backend/config.yaml`.

Important: Home Assistant Supervisor must be able to read this repository directly. If the repository is private, make it public or publish the add-on in a public release repository before installing from Store.

The repository contains the required root `repository.yaml` and the add-on directory `astro_weather_backend/`.

## What The Add-on Creates

After the first successful start the add-on publishes:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

When `install_dashboard_cards: true` is enabled, the add-on also creates `/config/www` if needed and writes:

```text
/config/www/astro-start-card.js
/config/www/moon-forecast-card.js
```

The JavaScript files are copied automatically. Lovelace resources are still a one-time Home Assistant dashboard setting.

## Dashboard Resource Activation

1. Start the add-on once and check the log for:

```text
KARTY: zapsano do /config/www: astro-start-card.js, moon-forecast-card.js
```

2. In a browser, verify that Home Assistant can serve the files:

```text
https://YOUR-HA/local/astro-start-card.js?v=17
https://YOUR-HA/local/moon-forecast-card.js?v=19
```

Both URLs should show JavaScript source, not `404: Not Found`.

3. Open **Settings -> Dashboards -> Resources**. In some Home Assistant versions the same screen is available at:

```text
/config/lovelace/resources
```

4. Add these resources as **JavaScript module**:

| URL | Resource type |
| --- | --- |
| `/local/astro-start-card.js?v=17` | JavaScript module |
| `/local/moon-forecast-card.js?v=19` | JavaScript module |

5. Refresh the browser page. If Home Assistant still says `Custom element doesn't exist`, use Ctrl+F5 or increase the cache suffix, for example from `?v=17` to `?v=18`.

## Dashboard Card YAML

Main decision card:

```yaml
type: custom:astro-start-card
decision_entity: sensor.astro_vhodnost_foceni
weather_entity: sensor.astro_weather_detail
moon_entity: sensor.mesic_foceni_predpoved
days: 3
grid_options:
  columns: full
```

Moon and longer forecast overview:

```yaml
type: custom:moon-forecast-card
entity: sensor.mesic_foceni_predpoved
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
days: 45
grid_options:
  columns: full
```

Both cards in one vertical stack:

```yaml
type: vertical-stack
cards:
  - type: custom:astro-start-card
    decision_entity: sensor.astro_vhodnost_foceni
    weather_entity: sensor.astro_weather_detail
    moon_entity: sensor.mesic_foceni_predpoved
    days: 3

  - type: custom:moon-forecast-card
    entity: sensor.mesic_foceni_predpoved
    weather_entity: sensor.astro_weather_detail
    decision_entity: sensor.astro_vhodnost_foceni
    days: 45
```

To add a card manually: open the dashboard, choose **Edit dashboard -> Add card -> Manual**, paste one of the YAML blocks above and save.

## Data Sources

- MET Norway Locationforecast: clouds, cloud layers, fog, precipitation, temperature, dew point, wind.
- CHMU ALADIN open data: low/mid/high/total cloud cover.
- Internal Moon calculation: astronomical night, Moon phase, illumination, altitude, hourly interference.
- Open-Meteo Air Quality API: CAMS AOD 550 and dust as surface concentration in `ug/m3`.
- 7Timer ASTRO JSON API: seeing and transparency index.

SkyAccuracy.cz is no longer used. If Open-Meteo/CAMS or 7Timer is unavailable, stale, or changes shape, AOD/seeing are ignored and the decision continues from MET + ALADIN + internal Moon.

## Troubleshooting

If the dashboard says `Custom element doesn't exist: astro-start-card`, Home Assistant has not loaded the JavaScript resource. Check that the file URL returns JavaScript, check the resource entry, then refresh the browser cache.

If the card loads but shows missing entities, wait for the add-on to finish the first forecast refresh and check that these entities exist in **Developer Tools -> States**:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

## Tests

Run from repository root:

```bash
python3 -m py_compile astro_weather_backend/astro_weather_backend.py
python3 -m unittest -v tests/test_astro_weather_backend.py
```
