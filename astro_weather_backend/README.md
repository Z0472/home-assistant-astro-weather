# Astro Weather Backend 12.1.4

Prepared 9 Sep 2026. Clean Home Assistant add-on version with internal Moon calculation, no SkyAccuracy dependency, automatic dashboard-card installation, and repository-based install/update instructions.

## What Changed

- The backend calculates astronomical night and Moon interference internally.
- No `numpy`, `skyfield`, `de440.bsp`, Moon script, command line sensor, or Home Assistant package sensor is needed.
- The backend publishes these Home Assistant entities through the Supervisor API:
  - `sensor.astro_weather_detail`
  - `sensor.astro_vhodnost_foceni`
  - `sensor.mesic_foceni_predpoved`
- `sensor.mesic_foceni_predpoved` is kept for dashboard-card compatibility, but it is no longer an input dependency.
- The add-on installs current dashboard card files to `/config/www` on startup when `install_dashboard_cards` is enabled.
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

- calculated internally without external files,
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
7. Optionally enable **Start on boot**, **Watchdog** and **Auto update**.

For later upgrades use **Check for updates** or enable **Auto update**. The Supervisor compares the installed app version with `astro_weather_backend/config.yaml`.

Important: Home Assistant Supervisor must be able to read the repository directly. If this repository is private, make it public or publish the add-on in a public release repository before installing from Store.

If Home Assistant still shows an old local test install, uninstall it and remove the old local app folder once. That is only cleanup for previous manual tests, not the normal install path.

## Home Assistant Entities

The add-on publishes these entities itself:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

No `command_line`, REST sensor package, external Moon integration, Python script, `numpy`, `skyfield`, or `de440.bsp` is required.

## Dashboard Card Files

The add-on image contains the dashboard cards and writes them on startup to:

```text
/config/www/astro-start-card.js
/config/www/moon-forecast-card.js
```

The option `install_dashboard_cards` controls this behavior and is enabled by default. If `/config/www` does not exist, the add-on creates it.

The add-on deliberately does not edit Home Assistant's internal `.storage` files, so Lovelace resources remain a one-time UI setting.

## Activate Dashboard Resources

1. Start the add-on once and check the log for:

```text
KARTY: zapsano do /config/www: astro-start-card.js, moon-forecast-card.js
```

2. Open these URLs in the same Home Assistant browser session:

```text
https://YOUR-HA/local/astro-start-card.js?v=17
https://YOUR-HA/local/moon-forecast-card.js?v=19
```

They should show JavaScript source. If they show `404: Not Found`, the files have not been copied yet or `install_dashboard_cards` is disabled.

3. Open **Settings -> Dashboards -> Resources**. In some Home Assistant versions this screen is available directly at:

```text
/config/lovelace/resources
```

4. Add these resources as **JavaScript module**:

| URL | Resource type |
| --- | --- |
| `/local/astro-start-card.js?v=17` | JavaScript module |
| `/local/moon-forecast-card.js?v=19` | JavaScript module |

5. Refresh the browser. If Home Assistant still says `Custom element doesn't exist`, use Ctrl+F5 or increase the cache suffix, for example from `?v=17` to `?v=18`.

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
Astro Weather Backend 12.1.4
KARTY: zapsano do /config/www: ...
KVALITA OBLOHY: ... CAMS/Open-Meteo AOD, ... 7Timer seeing
MESIC INTERNI: ...
HA ENTITY: publikovano sensor.astro_weather_detail, sensor.astro_vhodnost_foceni, sensor.mesic_foceni_predpoved
```

## Manual Entity Refresh

Use this in Home Assistant **Developer Tools -> Actions** in YAML mode:

```yaml
action: homeassistant.update_entity
data:
  entity_id:
    - sensor.astro_weather_detail
    - sensor.astro_vhodnost_foceni
    - sensor.mesic_foceni_predpoved
```

## Development Checks

From repository root:

```bash
python3 -m py_compile astro_weather_backend/astro_weather_backend.py
python3 -m unittest -v tests/test_astro_weather_backend.py
```
