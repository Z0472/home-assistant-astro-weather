# Astro Weather Backend 12.1.12

Prepared 10 Sep 2026. Home Assistant add-on with internal Moon calculation, direct weather sources, automatic dashboard-card file installation, and repository-based updates.

## What Changed

- The backend calculates astronomical night and Moon interference internally.
- The backend publishes these Home Assistant entities through the Supervisor API:
  - `sensor.astro_weather_detail`
  - `sensor.astro_vhodnost_foceni`
  - `sensor.mesic_foceni_predpoved`
- `sensor.mesic_foceni_predpoved` is kept for dashboard-card compatibility, but it is no longer an input dependency.
- The add-on installs the current versioned dashboard cards plus one stable loader and manifest to `/config/www`.
- In normal Lovelace storage mode it creates or migrates its resource entry automatically.
- Hour-card colors now use a blue-to-gray cloud-cover palette instead of traffic-light colors.
- An uncertain verdict caused by MET/ALADIN disagreement states the conflicting values explicitly.
- A watchdog restores the published states within one minute after Home Assistant Core restarts.
- Card source links point directly to CAMS/Open-Meteo and 7Timer.
- The default MET User-Agent is generic and does not publish a personal domain or observatory name.
- The bundled latitude, longitude and altitude are public-safe sample defaults; set the real observing location in the app configuration.

## Data Sources

- MET Norway Locationforecast: cloud cover, cloud layers, fog, precipitation, temperature, dew point, wind.
- CHMU ALADIN open data: mainly low/mid/high/total cloud cover.
- Internal Moon calculation: astronomical night, phase, illumination, altitude, hourly interference.
- Open-Meteo Air Quality API: CAMS aerosol optical depth, AOD 550.
- Open-Meteo Air Quality API: CAMS dust as surface concentration in `ug/m3`.
- 7Timer ASTRO JSON API: seeing and transparency index; seeing is converted to estimated arcsec.

SkyAccuracy.cz is not used in this version. If Open-Meteo/CAMS or 7Timer is unavailable, stale, or changes format, AOD/seeing are ignored and the decision continues from MET + ALADIN + internal Moon.

Open-Meteo dust is not dust AOD 550. The backend stores it separately as `dust_ugm3` / `dustUgm3` and treats it as informational only.

## Decision changes in 12.1.12

- A continuous good block still has to be at least 4 hours long.
- The default latest block start is 120 minutes after astronomical darkness begins.
- Dew-point margin is a soft atmospheric haze/fog-risk factor because optics can be heated.
- MET `fog_area_fraction` remains a separate strong fog penalty/veto.
- Hourly output includes `scorePenalties` and `dominantPenalty`; the card shows the largest point loss.

## Default Rules

AOD:

- up to `0.10`: no penalty,
- above `0.10`: gradually lowers hourly score,
- from `0.30`: marks the hour as uncertain,
- from `0.40`: marks the hour as bad.

Seeing:

- up to about `1.0"`: very good,
- below `1.8"`: no penalty,
- from `1.8"`: lowers score and makes the hour less certain,
- from `2.5"`: can remove the hour from a good continuous block.

Moon:

- calculated internally by the backend,
- default interference starts at illumination >= `15 %` and Moon altitude above `0 deg`,
- with `use_moon: false`, Moon data is still published but no longer vetoes imaging hours.

## Install / Update From GitHub

Use the Home Assistant App/Add-on Store repository flow. No files from this repository need to be copied into `/addons`.

1. In Home Assistant open **Settings -> Apps -> Install app**.
2. Open the three-dot menu and choose **Repositories**.
3. Add this repository URL:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

4. Install **Astro Weather Backend** from the store.
5. Open the add-on configuration and set at least:

```yaml
latitude: 50.0755
longitude: 14.4378
altitude: 250
timezone: Europe/Prague
```

Use your real observing location values here.

6. Start the add-on.
7. Wait until the log shows both `MESIC INTERNI` and `HA ENTITY: publikovano`.
8. Optionally enable **Start on boot**, **Watchdog** and **Auto update**.
9. Continue with **Check Dashboard Resource** below.

For later upgrades use **Check for updates** or enable **Auto update**. The Supervisor compares the installed app version with `astro_weather_backend/config.yaml`; the stable card loader selects the new versioned JavaScript files automatically.

Important: Home Assistant Supervisor must be able to read the repository directly. If this repository is private, make it public or publish the add-on in a public release repository before installing from Store.

If Home Assistant still shows an old local test install, uninstall it and remove the old local app folder once. That is only cleanup for previous manual tests, not the normal install path.

## Home Assistant Entities

The add-on publishes these entities itself:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

## Dashboard Card Files

The add-on image contains the dashboard cards and writes them on startup to:

```text
/config/www/astro-start-card-v22.js
/config/www/moon-forecast-card-v23.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

The option `install_dashboard_cards` controls this behavior and is enabled by default. If `/config/www` does not exist, the add-on creates it.

In Lovelace storage mode, the add-on uses Home Assistant's authenticated WebSocket API to maintain this single JavaScript module resource:

```text
/local/astro-weather-cards-loader.js
```

Existing Astro resource entries with physical version numbers are migrated to the loader and duplicate Astro entries are removed. Resources belonging to other cards are not changed.

## Check Dashboard Resource

1. Start the add-on once and check the log for:

```text
KARTY: prepsano v /config/www: astro-start-card-v22.js [...], moon-forecast-card-v23.js [...], astro-weather-cards-loader.js, astro-weather-cards-manifest.json
KARTY RESOURCE: ... /local/astro-weather-cards-loader.js ...
HA ENTITY: publikovano sensor.astro_weather_detail, sensor.astro_vhodnost_foceni, sensor.mesic_foceni_predpoved
```

2. Open these URLs in the same Home Assistant browser session:

```text
https://YOUR-HA/local/astro-weather-cards-loader.js
https://YOUR-HA/local/astro-weather-cards-manifest.json
https://YOUR-HA/local/astro-start-card-v22.js
https://YOUR-HA/local/moon-forecast-card-v23.js
```

The loader and cards should show JavaScript source and the manifest should show JSON. If they show `404: Not Found`, the files have not been copied yet or `install_dashboard_cards` is disabled.

3. Open **Settings -> Dashboards -> Resources**. In some Home Assistant versions this screen is available directly at:

```text
/config/lovelace/resources
```

4. Verify that there is exactly this one Astro resource:

| URL | Resource type |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

The add-on creates or migrates this entry automatically. If `lovelace.resource_mode` is `yaml`, automatic storage changes are unavailable; add the loader once to the YAML `resources` section instead.

If the log ends with `KARTY RESOURCE CHYBA`, add only `/local/astro-weather-cards-loader.js` manually as a JavaScript module and remove the two old Astro Weather entries. This is a fallback; normal storage-mode installations need no manual resource edit.

5. Restart Home Assistant after the first installation, or refresh the Home Assistant frontend after an upgrade. The first restart is required when the add-on created `/config/www` after Home Assistant had already started.
6. Wait up to one minute for the add-on to restore its published states after the Home Assistant restart.
7. Verify all three entities in **Developer Tools -> States**, then add the card YAML below.

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

## Verify

The log should contain:

```text
Astro Weather Backend 12.1.12
KARTY: prepsano v /config/www: ...
KARTY RESOURCE: ... /local/astro-weather-cards-loader.js ...
KVALITA OBLOHY: ... CAMS/Open-Meteo AOD, ... 7Timer seeing
MESIC INTERNI: ...
HA ENTITY: publikovano sensor.astro_weather_detail, sensor.astro_vhodnost_foceni, sensor.mesic_foceni_predpoved
```

After a Home Assistant restart, the log can also contain:

```text
HA ENTITY: obnoveno po restartu Home Assistantu: ...
```

If the entities are still missing after one minute, restart **Astro Weather Backend** once and check its log for `HA ENTITY CHYBA`.

## Development Checks

From repository root:

```bash
python3 -m py_compile astro_weather_backend/astro_weather_backend.py
python3 -m unittest -v tests/test_astro_weather_backend.py
```
