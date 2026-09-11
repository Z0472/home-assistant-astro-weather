# Dashboard Cards

The current card sources are kept here as TXT files for easy download and inspection:

- `astro-start-card-v22.txt`
- `moon-forecast-card-v23.txt`

The same cards are bundled inside the add-on image and copied automatically on startup to:

```text
/config/www/astro-start-card-v22.js
/config/www/moon-forecast-card-v23.js
/config/www/astro-weather-cards-loader.js
/config/www/astro-weather-cards-manifest.json
```

The TXT files are still useful as a manual fallback, but the normal install path is the add-on.

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

If Home Assistant uses YAML resource mode, add the loader once to `lovelace.resources`. Then restart Home Assistant after the first installation or refresh its frontend after an upgrade.

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
https://YOUR-HA/local/astro-start-card-v22.js
https://YOUR-HA/local/moon-forecast-card-v23.js
```

The loader and cards must show JavaScript source and the manifest must show JSON. If they return `404: Not Found`, the add-on has not copied the files yet or `install_dashboard_cards` is disabled.
