# Dashboard Cards

The current card sources are kept here as TXT files for easy download and inspection:

- `astro-start-card-v20.txt`
- `moon-forecast-card-v23.txt`

The same cards are bundled inside the add-on image and copied automatically on startup to:

```text
/config/www/astro-start-card-v20.js
/config/www/moon-forecast-card-v23.js
```

The TXT files are still useful as a manual fallback, but the normal install path is the add-on.

## Enable Lovelace Resources

The add-on copies the JavaScript files into `/config/www`. Add the Lovelace resource entries manually:

In Home Assistant open **Settings -> Dashboards -> Resources** and add:

| URL | Resource type |
| --- | --- |
| `/local/astro-start-card-v20.js` | JavaScript module |
| `/local/moon-forecast-card-v23.js` | JavaScript module |

If the Resources page is not visible, try the direct Home Assistant path:

```text
/config/lovelace/resources
```

Use exactly one entry for each card and remove every older entry whose URL is not identical to one of the two paths above. Then restart Home Assistant. Open the resource URL directly to verify that it shows JavaScript rather than `404`.

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
https://YOUR-HA/local/astro-start-card-v20.js
https://YOUR-HA/local/moon-forecast-card-v23.js
```

They must show JavaScript source. If they return `404: Not Found`, the add-on has not copied the files yet or `install_dashboard_cards` is disabled.
