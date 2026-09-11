# Home Assistant Astro Weather

Home Assistant app/add-on for astrophotography planning. It combines MET Norway Locationforecast, CHMU ALADIN, DWD ICON, internal Moon/night calculation, CAMS/Open-Meteo AOD 550, Open-Meteo dust concentration and 7Timer seeing into one practical decision: **SPUSTIT / NEJISTE / NESPOUSTET** (START / UNCERTAIN / DO NOT START).

## Repository Description

Suggested GitHub **About -> Description** text:

```text
Home Assistant add-on for astrophotography weather decisions using MET Norway, CHMU ALADIN, DWD ICON, internal Moon, CAMS/Open-Meteo AOD and 7Timer seeing.
```

Suggested GitHub topics:

```text
home-assistant, addon, astronomy, astrophotography, weather, aladin, icon, cams, moon, seeing, 7timer
```

## Current Version

**Astro Weather Backend 12.2.0**

Version 12.2.0 adds a third independent cloud-model family and a location-independent consensus layer:

- MET Norway Locationforecast remains the primary general weather source,
- CHMU ALADIN remains a high-resolution regional cloud source and is used only when the configured location is close to its native grid,
- DWD ICON is fetched through the Open-Meteo DWD ICON interface using the explicit `dwd_icon_seamless` model family,
- the three cloud forecasts are combined by a robust median/spread consensus rather than fixed invented model weights or simple 2-of-3 voting,
- a lone outlier lowers confidence but does not automatically overrule two closely agreeing models,
- a genuine wide three-way conflict produces low confidence / an uncertain hour,
- if ICON is unavailable the old two-model MET + ALADIN cloud formula is preserved,
- if only one independent cloud model is available it cannot create a normal good block by itself.

The DWD seamless family is geographically portable: where available it blends the appropriate DWD ICON Global, ICON EU and ICON D2 products. This keeps the add-on useful outside the Czech Republic instead of hard-coding South Bohemia or one country.

The backend also calculates the Moon and astronomical night internally, publishes weather/Moon/decision entities directly to Home Assistant, installs dashboard cards itself, and maintains one stable Lovelace loader selected through a no-cache manifest.

The backend app publishes these Home Assistant entities itself through the Supervisor API:

- `sensor.astro_weather_detail`
- `sensor.astro_vhodnost_foceni`
- `sensor.mesic_foceni_predpoved`

The Moon entity is a compatibility output for existing dashboard cards, not an input dependency.

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
6. Keep `use_icon: true` unless you intentionally want to disable the DWD ICON source.
7. Start the add-on.
8. Wait until the log shows `ICON:`, `MESIC INTERNI` and `HA ENTITY: publikovano`. If ICON is temporarily unavailable, the backend continues with the remaining independent models.
9. Optionally enable **Start on boot**, **Watchdog** and **Auto update**.
10. Continue with **Dashboard Resource Check** below.

Future upgrades are handled by Home Assistant through **Check for updates** or **Auto update**. The add-on updates its cards and the stable loader automatically; users do not change versioned Lovelace resource URLs.

## What The Add-on Creates

After the first successful start the add-on publishes:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

When `install_dashboard_cards: true` is enabled, version 12.2.0 installs the decision card v23, its stable v22 base module, the Moon card, the loader and manifest:

```text
/config/www/astro-start-card-base-v22.js
/config/www/astro-start-card-v23.js
/config/www/moon-forecast-card-v23.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

The v22 base is an internal implementation module. Lovelace must still contain only the stable loader resource; do not add the base module manually.

In normal Home Assistant storage mode, the add-on creates or updates this one Lovelace resource automatically:

```text
/local/astro-weather-cards-loader.js
```

On upgrade, older Astro resource entries such as `astro-start-card-v20.js`, `astro-start-card-v22.js` or old Moon-card resource entries are consolidated to this loader. Other Lovelace resources are never changed.

## Dashboard Resource Check

1. Start the add-on once and check the log for card installation, the stable loader and published entities.
2. In a browser, verify that these URLs return JavaScript/JSON rather than `404: Not Found`:

```text
https://YOUR-HA/local/astro-weather-cards-loader.js
https://YOUR-HA/local/astro-weather-cards-manifest.json
https://YOUR-HA/local/astro-start-card-v23.js
https://YOUR-HA/local/astro-start-card-base-v22.js
https://YOUR-HA/local/moon-forecast-card-v23.js
```

3. Open **Settings -> Dashboards -> Resources**. In some Home Assistant versions the same screen is available at:

```text
/config/lovelace/resources
```

4. Verify that there is exactly this one Astro resource:

| URL | Resource type |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

The add-on normally creates it and removes its own older versioned entries automatically. If automatic registration is unavailable because `lovelace.resource_mode` is `yaml`, add the loader once to the `resources` section of the Home Assistant configuration.

If the log ends with `KARTY RESOURCE CHYBA`, add only `/local/astro-weather-cards-loader.js` manually as a JavaScript module and remove old Astro Weather resource entries.

5. Restart Home Assistant after the first installation, or refresh the Home Assistant frontend after an upgrade.
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

## Cloud Model Consensus

The cloud consensus deliberately does not assign arbitrary permanent weights such as "ALADIN 40 %, ICON 35 %, ECMWF 25 %".

With three independent model values it uses the median as the robust center and adds 20 % of the full inter-model spread as a conservative cloud correction. Model spread remains visible as a separate confidence signal. A tight pair plus one distant model is treated as an outlier case; a broad disagreement without a tight pair is treated as a genuine conflict.

With only MET + ALADIN available, the 12.1.12 two-model cloud formula and high-cloud safeguard are retained exactly. With one model, confidence is intentionally capped so that one source alone cannot claim a normal high-confidence imaging window.

This is a forecast consensus, not a claim that model grid resolution equals forecast skill. Future versions can add locally verified skill weights after enough observations exist; version 12.2.0 does not invent those weights.

## Data Sources

- MET Norway Locationforecast: clouds, cloud layers, fog, precipitation, temperature, dew point and wind. The underlying model family depends on MET Norway coverage and forecast horizon.
- CHMU ALADIN open data: low/mid/high/total cloud cover; the backend validates proximity to the native ALADIN grid before using it.
- DWD ICON via Open-Meteo DWD ICON API: total/low/mid/high cloud cover from the DWD ICON seamless model family.
- Internal Moon calculation: astronomical night, Moon phase, illumination, altitude and hourly interference.
- Open-Meteo Air Quality API: CAMS AOD 550 and dust as surface concentration in `ug/m3`.
- 7Timer ASTRO JSON API: seeing and transparency index.

## Troubleshooting

If the dashboard says `Custom element doesn't exist: astro-start-card`, verify that the loader, manifest, `astro-start-card-v23.js` and `astro-start-card-base-v22.js` URLs open correctly, keep only the stable loader resource shown above, and refresh/restart Home Assistant.

If ICON is unavailable, check the add-on log for `ICON CHYBA`. This should not stop the application; valid MET/ALADIN data continue through the proven two-model path.

If a card loads but shows missing entities, first wait for `HA ENTITY: publikovano` in the add-on log. The backend restores missing states within one minute. Check these entities in **Developer Tools -> States**:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

If they are still missing, restart **Astro Weather Backend** once and check the add-on log for `HA ENTITY CHYBA`.

## Tests

GitHub Actions compiles all Python modules, checks the v23 JavaScript syntax, then runs the original 12.1 regression suite and the new ICON/multi-model regression suite independently.

Run from repository root:

```bash
python3 -m py_compile astro_weather_backend/astro_weather_backend.py
python3 -m py_compile astro_weather_backend/weather_models.py
python3 -m py_compile astro_weather_backend/cloud_consensus.py
python3 -m py_compile astro_weather_backend/model_runtime.py
python3 -m py_compile astro_weather_backend/app.py
node --check astro_weather_backend/cards/astro-start-card-v23.js
python3 -m unittest -v tests/test_astro_weather_backend.py
python3 -m unittest -v tests/test_model_consensus.py
```
