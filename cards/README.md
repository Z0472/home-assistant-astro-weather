# Dashboard Cards

The current card sources are kept here as TXT files for easy download and inspection:

- `astro-start-card-v25.txt`
- `moon-forecast-card-v25.txt`

The same current cards are bundled inside the add-on image and copied automatically on startup to `/config/www/` together with their required dependency modules and the stable loader. The current physical entry modules are:

```text
/config/www/astro-start-card-v25.js
/config/www/moon-forecast-card-v25.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

The TXT files are a manual inspection/fallback copy. The normal install path is the add-on.

## Lovelace Resource

The add-on copies the JavaScript files into `/config/www` and, in normal Lovelace storage mode, automatically creates or migrates a single stable resource:

In Home Assistant open **Settings -> Dashboards -> Resources** and verify:

| URL | Resource type |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

If the Resources page is not visible, try the direct Home Assistant path:

```text
/config/lovelace/resources
```

The loader reads `/local/astro-weather-cards-manifest.json` without browser caching and imports the current physical card versions. Future updates therefore do not require changing Lovelace URLs. Existing `astro-start-card-vNN.js` and `moon-forecast-card-vNN.js` entries are consolidated automatically; unrelated resources are left untouched.

After an upgrade use a hard browser refresh (`Ctrl+F5`) if Home Assistant still shows an older already-loaded custom element.

## Current v25 behavior

- `Důvěra` is shown as **Shoda modelů**, because the percentage represents inter-model agreement, not a calibrated probability that the forecast will be correct.
- A cloud-only `NESPOUŠTĚT` is softened to `NEJISTÉ` when model agreement is below 60 % and no hard veto is present.
- Hard vetoes such as precipitation, fog, excessive wind, interfering Moon, bad AOD or bad seeing still keep `NESPOUŠTĚT`.
- The hourly strip runs from apparent sunset to the following sunrise, while the operational imaging decision still uses only astronomical darkness.
- Nighttime hourly weather icons never use a Sun symbol; partly cloudy night hours use the Moon/night variant.

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

## Quick Checks

Open these URLs in the same Home Assistant browser session:

```text
https://YOUR-HA/local/astro-weather-cards-loader.js
https://YOUR-HA/local/astro-weather-cards-manifest.json
https://YOUR-HA/local/astro-start-card-v25.js
https://YOUR-HA/local/moon-forecast-card-v25.js
```

The loader and cards must show JavaScript source and the manifest must show JSON. If they return `404: Not Found`, the add-on has not copied the files yet or `install_dashboard_cards` is disabled.
