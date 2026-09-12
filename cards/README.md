# Dashboard Cards

The current manual-inspection/fallback sources are:

- `astro-start-card-v27.txt`
- `moon-forecast-card-v25.txt`

The normal install path is the Home Assistant app. It copies all required JavaScript modules to `/config/www` and maintains one stable Lovelace resource.

## Current Entry Modules

```text
/config/www/astro-start-card-v27.js
/config/www/moon-forecast-card-v25.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

Older module layers required by v27/v25 are installed automatically. They are implementation dependencies, not separate Lovelace resources.

## Lovelace Resource

In Home Assistant open **Settings -> Dashboards -> Resources** and verify exactly this Astro Weather resource:

| URL | Resource type |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

The loader reads `/local/astro-weather-cards-manifest.json` without browser caching and imports the current card versions. Future app updates therefore do not require editing Lovelace resource URLs.

After an upgrade use **Ctrl+F5** if Home Assistant still displays an already loaded older custom element.

## v27 Decision Card

The card deliberately separates two questions:

1. **Aktuální trend** — modelled spatial situation relative to the current time. Relative ETA such as `za 45 min` is used only here.
2. **Předpověď noci** — development across the sunset-to-sunrise strip. Changes are shown with absolute clock times such as `vyjasnění kolem 23:00`.

Each hourly tile also receives one compact trend arrow:

```text
↗ zatahování
↘ vyjasňování
→ setrvalý stav
```

The main card stays intentionally compact. Detailed centre/min/max cloud, spatial stability, contributing sources, cloud-edge distance/direction and pressure-level wind remain in tooltips/entity attributes rather than crowding the card.

Other current behavior:

- `Shoda modelů` is inter-model agreement, not a forecast-success probability.
- A cloud-only `NESPOUŠTĚT` can become `NEJISTÉ` when model agreement is weak.
- Hard vetoes remain authoritative.
- The hourly strip runs from sunset to sunrise, while the operational decision uses only astronomical darkness.
- Nighttime hourly icons do not use a Sun symbol.
- The backend restores its last valid state immediately after restart while a fresh forecast is recalculated.

## Card YAML

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

Moon / long-range overview:

```yaml
type: custom:moon-forecast-card
entity: sensor.mesic_foceni_predpoved
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
days: 45
grid_options:
  columns: full
```

Both cards:

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

## Quick Checks

Open these URLs in the same Home Assistant browser session:

```text
https://YOUR-HA/local/astro-weather-cards-loader.js
https://YOUR-HA/local/astro-weather-cards-manifest.json
https://YOUR-HA/local/astro-start-card-v27.js
https://YOUR-HA/local/moon-forecast-card-v25.js
```

If they return `404: Not Found`, the app has not copied the files yet or `install_dashboard_cards` is disabled.
