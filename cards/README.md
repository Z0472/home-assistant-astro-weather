# Dashboard Cards

The current card sources are kept here as TXT files for easy download and inspection:

- `astro-start-card-v18.txt`
- `moon-forecast-card-v20.txt`

The same cards are bundled inside the add-on image and copied automatically on startup to:

```text
/config/www/astro-start-card.js
/config/www/moon-forecast-card.js
```

The TXT files are still useful as a manual fallback, but the normal install path is now the add-on.

## Enable Lovelace Resources

The add-on copies JavaScript files into `/config/www`, but Home Assistant still needs one-time Lovelace resource entries.

In Home Assistant open **Settings -> Dashboards -> Resources** and add:

| URL | Resource type |
| --- | --- |
| `/local/astro-start-card.js?v=18` | JavaScript module |
| `/local/moon-forecast-card.js?v=20` | JavaScript module |

If the Resources page is not visible, try the direct Home Assistant path:

```text
/config/lovelace/resources
```

After adding or changing a resource, refresh the browser. If the card still does not load, use Ctrl+F5 or raise the query suffix, for example `?v=18` to `?v=19`.

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
https://YOUR-HA/local/astro-start-card.js?v=18
https://YOUR-HA/local/moon-forecast-card.js?v=20
```

They must show JavaScript source. If they return `404: Not Found`, the add-on has not copied the files yet or `install_dashboard_cards` is disabled.
