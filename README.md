# Home Assistant Astro Weather

Home Assistant app/add-on for astrophotography planning. It combines MET Norway, CHMU ALADIN, internal Moon/night calculation, CAMS/Open-Meteo AOD 550, Open-Meteo dust concentration and 7Timer seeing into one practical decision: **SPUSTIT / NEJISTE / NESPOUSTET** (START / UNCERTAIN / DO NOT START).

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

**Astro Weather Backend 12.1.11**

This version is designed for a clean Home Assistant install:

- the backend calculates the Moon and astronomical night internally,
- weather, Moon and the imaging decision are published directly to Home Assistant,
- dashboard card files are installed by the add-on,
- one stable Lovelace loader is created and maintained automatically in storage mode,
- future card versions are selected from a no-cache manifest, so their resource URLs no longer need manual edits.

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
7. Wait until the log shows both `MESIC INTERNI` and `HA ENTITY: publikovano`.
8. Optionally enable **Start on boot**, **Watchdog** and **Auto update**.
9. Continue with **Dashboard Resource Check** below.

Future upgrades are handled by Home Assistant through **Check for updates** or **Auto update**. The add-on updates its cards and the stable loader automatically; users do not change versioned Lovelace resource URLs.

Important: Home Assistant Supervisor must be able to read this repository directly. If the repository is private, make it public or publish the add-on in a public release repository before installing from Store.

The repository contains the required root `repository.yaml` and the add-on directory `astro_weather_backend/`.

## What The Add-on Creates

After the first successful start the add-on publishes:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

When `install_dashboard_cards: true` is enabled, the add-on also creates `/config/www` if needed and installs the current versioned cards plus a stable loader and manifest:

```text
/config/www/astro-start-card-v21.js
/config/www/moon-forecast-card-v23.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

In normal Home Assistant storage mode, the add-on also creates or updates a single Lovelace resource automatically:

```text
/local/astro-weather-cards-loader.js
```

On upgrade, older Astro resource entries such as `astro-start-card-v20.js`, `moon-forecast-card-v22.js` or `moon-forecast-card-v23.js` are consolidated to this loader. Other Lovelace resources are never changed.

## Dashboard Resource Check

1. Start the add-on once and check the log for:

```text
KARTY: prepsano v /config/www: astro-start-card-v21.js [...], moon-forecast-card-v23.js [...], astro-weather-cards-loader.js, astro-weather-cards-manifest.json
KARTY RESOURCE: ... /local/astro-weather-cards-loader.js ...
HA ENTITY: publikovano sensor.astro_weather_detail, sensor.astro_vhodnost_foceni, sensor.mesic_foceni_predpoved
```

2. In a browser, verify that Home Assistant can serve the files:

```text
https://YOUR-HA/local/astro-weather-cards-loader.js
https://YOUR-HA/local/astro-weather-cards-manifest.json
https://YOUR-HA/local/astro-start-card-v21.js
https://YOUR-HA/local/moon-forecast-card-v23.js
```

The loader and cards should show JavaScript source and the manifest should show JSON, not `404: Not Found`.

3. Open **Settings -> Dashboards -> Resources**. In some Home Assistant versions the same screen is available at:

```text
/config/lovelace/resources
```

4. Verify that there is exactly this one Astro resource:

| URL | Resource type |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

The add-on normally creates it and removes its own older versioned entries automatically. If automatic registration is unavailable because `lovelace.resource_mode` is `yaml`, add the loader once to the `resources` section of the Home Assistant configuration.

If the log ends with `KARTY RESOURCE CHYBA`, add only `/local/astro-weather-cards-loader.js` manually as a JavaScript module and remove the two old Astro Weather entries. This is a fallback; normal storage-mode installations need no manual resource edit.

5. Restart Home Assistant after the first installation, or refresh the Home Assistant frontend after an upgrade. The first restart is required when the add-on created `/config/www` after Home Assistant had already started.
6. Wait up to one minute. The add-on checks the three published states and restores them automatically after a Home Assistant restart.
7. Verify the entities in **Developer Tools -> States**, then add the card YAML below.

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

## Troubleshooting

If the dashboard says `Custom element doesn't exist: astro-start-card`, verify that the loader, manifest and current versioned file URLs open correctly, keep only the stable loader resource shown above, and restart Home Assistant.

If a card loads but shows missing entities, first wait for `HA ENTITY: publikovano` in the add-on log. After a Home Assistant restart, version 12.1.11 restores missing states within one minute. Check these entities in **Developer Tools -> States**:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

If they are still missing, restart **Astro Weather Backend** once and check the add-on log for `HA ENTITY CHYBA`.

## Tests

Run from repository root:

```bash
python3 -m py_compile astro_weather_backend/astro_weather_backend.py
python3 -m unittest -v tests/test_astro_weather_backend.py
```
