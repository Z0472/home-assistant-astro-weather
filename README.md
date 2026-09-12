# Home Assistant Astro Weather

Home Assistant app/add-on for astrophotography planning. It combines MET Norway Locationforecast, CHMI ALADIN, DWD ICON, spatial cloud analysis, internal Moon/night calculation, CAMS/Open-Meteo AOD 550 and 7Timer seeing into one operational decision: **SPUSTIT / NEJISTÉ / NESPOUŠTĚT**.

## Current Version

**Astro Weather Backend 12.3.0**

Version 12.3.0 adds a spatial cloud-neighbourhood layer. The normal point forecast remains the core forecast, but the backend also checks the surroundings of the configured observing site so a slightly misplaced model cloud boundary is less likely to produce an overconfident decision.

The spatial layer is intentionally conservative: it may downgrade an otherwise confident result to **NEJISTÉ**, but it never overrides a hard veto and never upgrades a bad forecast directly to **SPUSTIT**.

## Main Data Sources

- **MET Norway Locationforecast**: point forecast for general weather, cloud layers, fog, precipitation, temperature, dew point and wind.
- **CHMI ALADIN**: high-resolution regional cloud forecast from native GRIB data; the backend validates that the configured site is close to the model grid.
- **DWD ICON Seamless via Open-Meteo**: total/low/mid/high cloud cover and the spatial cloud-neighbourhood forecast.
- **Internal Moon calculation**: astronomical night, phase, illumination, altitude and hourly interference.
- **CAMS/Open-Meteo Air Quality**: AOD 550 and informational dust concentration.
- **7Timer ASTRO**: model seeing estimate.

SkyAccuracy.cz is not used.

## Decision Philosophy

The dashboard should stay simple even though the backend is not. The user should not have to compare several meteorological websites manually.

The central decision uses:

- model consensus from MET / ALADIN / ICON,
- astronomical darkness and Moon interference,
- precipitation, fog and wind vetoes,
- AOD and seeing quality factors,
- spatial cloud stability around the observing site.

`Shoda modelů` means agreement between independent forecast models; it is **not** a calibrated probability that the forecast will be correct.

Hard vetoes such as precipitation, strong fog/wind, interfering Moon, bad AOD or bad seeing remain authoritative. A cloud-only `NESPOUŠTĚT` is softened to `NEJISTÉ` when model agreement is weak.

## Spatial Cloud Analysis (12.3.0)

Spatial analysis is enabled by default:

```yaml
spatial_cloud_analysis: true
spatial_radius_km: 30
```

`spatial_radius_km` can be set from **10 to 50 km**.

The backend samples **17 locations**:

- observing site,
- 8 compass directions at half the configured radius,
- 8 compass directions at the full radius.

DWD ICON supplies the neighbourhood cloud field in one multi-location request. ALADIN reuses its already downloaded cloud GRIB and samples the same neighbourhood locally. MET remains a point forecast in this version.

The backend derives, when enough data are available:

- spatial cloud range and stability,
- whether the site lies near a cloud boundary,
- approximate direction and distance of the nearest 50% cloud boundary,
- whether cloud is approaching or clearing in successive forecast hours,
- a rough ETA for a meaningful change over the site,
- dominant ICON cloud layer and pressure-level wind as a consistency check.

The card deliberately shows only a compact operational message, for example:

```text
✓ Okolí stabilně jasné
☁ Oblačnost přichází ~1 h 15 min od Z
🌙 Vyjasnění ~45 min
⚠ Hrana oblačnosti v okolí · ~14 km Z
```

Detailed diagnostics remain in entity attributes/tooltips rather than cluttering the main card.

## Sunset-to-Sunrise Hourly Strip

The hourly visual strip runs from apparent **sunset to the following sunrise**, so evening clearing or incoming clouds are visible before astronomical darkness begins. The actual photography decision and good-block calculation still use only **astronomical darkness**.

Nighttime cloud icons use nighttime/Moon variants; the hourly night strip does not show a Sun symbol.

## Automatic Install From GitHub

1. In Home Assistant open **Settings -> Apps -> Install app**.
2. Open the three-dot menu and choose **Repositories**.
3. Add:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

4. Install **Astro Weather Backend**.
5. Set at least `latitude`, `longitude`, `altitude` and `timezone`.
6. Leave `use_icon: true` and `spatial_cloud_analysis: true` enabled unless you intentionally want to disable those layers.
7. Select a spatial radius from 10–50 km; **30 km is the default**.
8. Start the app and check the log for weather sources, internal Moon and published Home Assistant entities.
9. Optionally enable **Start on boot**, **Watchdog** and **Auto update**.

Future versions are installed through Home Assistant **Check for updates** / **Auto update**.

## Home Assistant Entities

The app publishes:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

The central verdict and spatial summary are in `sensor.astro_vhodnost_foceni`.

## Dashboard Cards

The app installs the current card modules into `/config/www` and maintains one stable Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

Current entry modules are:

```text
/config/www/astro-start-card-v26.js
/config/www/moon-forecast-card-v25.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

Dependency modules for older card layers are installed automatically. Do **not** add individual versioned cards as Lovelace resources.

In **Settings -> Dashboards -> Resources** there should be exactly one Astro Weather resource:

| URL | Resource type |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

After an upgrade use **Ctrl+F5** if the browser still displays an already cached custom element.

## Dashboard Card YAML

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

## Cloud Model Consensus

With three independent model values the cloud consensus uses a robust median/spread approach rather than fixed arbitrary model weights. A tight pair can resist one distant outlier; a broad conflict reduces model agreement and can make the result uncertain.

When ICON is unavailable, the proven MET + ALADIN two-model path remains available. When ALADIN is unavailable outside its supported region, MET + ICON can continue. The optional AOD, seeing and spatial layers are fail-open: failure of an advisory source must not crash the base forecast.

## Troubleshooting

If the dashboard says `Custom element doesn't exist: astro-start-card`, verify that these URLs open in the same Home Assistant browser session:

```text
https://YOUR-HA/local/astro-weather-cards-loader.js
https://YOUR-HA/local/astro-weather-cards-manifest.json
https://YOUR-HA/local/astro-start-card-v26.js
https://YOUR-HA/local/moon-forecast-card-v25.js
```

Keep only `/local/astro-weather-cards-loader.js` as the Astro Lovelace resource, then use **Ctrl+F5**.

If the spatial layer is unavailable, the base forecast continues. Check the app log for `PROSTOR ICON VAROVANI` or `PROSTOR ALADIN VAROVANI`.

## Development Checks

GitHub Actions compile all Python modules, validate card JavaScript syntax, run the stable regression suites plus spatial-cloud tests, and build the Home Assistant container.

Important local checks include:

```bash
python3 -m py_compile astro_weather_backend/spatial_cloud_patch.py
python3 -m unittest -v tests/test_spatial_cloud_patch.py
python3 -m unittest -v tests/test_release_wiring.py
node --check astro_weather_backend/cards/astro-start-card-v26.js
```
