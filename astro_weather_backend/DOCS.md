# Astro Weather Backend - dokumentace

Astro Weather je určeno pro plánování astrofotografie a automatizované provozní rozhodnutí, zda má smysl observatoř pro danou noc spouštět.

> UI a dokumentace jsou zatím pouze česky. Projekt je primárně určen pro Českou republiku, protože využívá regionální model ČHMÚ ALADIN.

## Nejdřív nastav polohu observatoře

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
```

Použij skutečnou polohu dalekohledu.

## Doporučené funkce

```yaml
use_icon: true
use_moon: true
use_aerosols: true
use_seeing: true
spatial_cloud_analysis: true
spatial_radius_km: 30
use_satellite: true
satellite_radius_km: 30
satellite_refresh_minutes: 10
install_dashboard_cards: true
install_lovelace_resources: true
```

## EUMETSAT

Pro kvantitativní MTG/FCI Cloud Mask vyplň EUMETSAT API údaje:

```yaml
eumetsat_consumer_key: "TVUJ_CONSUMER_KEY"
eumetsat_consumer_secret: "TVUJ_CONSUMER_SECRET"
```

Bez nich zůstávají meteorologické modely, Měsíc, AOD a seeing funkční; pouze kvantitativní satelitní CLM vrstva nebude dostupná.

## Dashboard resource

Aplikace udržuje jeden stabilní Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

Nepřidávej jednotlivé verzované JavaScript soubory jako samostatné resources.

## Kompletní návody

- Instalace: https://github.com/Z0472/home-assistant-astro-weather/blob/main/INSTALACE.md
- Konfigurace: https://github.com/Z0472/home-assistant-astro-weather/blob/main/KONFIGURACE.md
- Satelit: https://github.com/Z0472/home-assistant-astro-weather/blob/main/SATELLITE.md
- Přehled projektu: https://github.com/Z0472/home-assistant-astro-weather
