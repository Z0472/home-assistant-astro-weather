# Astro Weather Backend

Home Assistant App/Add-on pro provozní rozhodování o astrofotografické noci.

Backend kombinuje:

- MET Norway Locationforecast,
- ČHMÚ ALADIN,
- DWD ICON,
- prostorovou analýzu oblačnosti,
- interní výpočet astronomické noci a Měsíce,
- CAMS/Open-Meteo AOD,
- 7Timer seeing,
- EUMETSAT MTG/FCI Cloud Mask a IR10.5.

Výsledkem je jeden hlavní verdikt:

**SPUSTIT / NEJISTÉ / NESPOUŠTĚT**

> UI i dokumentace jsou zatím pouze česky. Projekt je primárně zaměřen na observatoře v České republice kvůli použití regionálního modelu ČHMÚ ALADIN.

## Instalace

Repozitář pro Home Assistant:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

Po instalaci nastav skutečnou polohu observatoře:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
```

Potom aplikaci spusť a zkontroluj vytvoření entit:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

Pro kvantitativní EUMETSAT CLM doplň také consumer key a consumer secret.

## Dokumentace

Kompletní dokumentace je v kořeni repozitáře:

- [Instalace](../INSTALACE.md)
- [Konfigurace](../KONFIGURACE.md)
- [Satelit EUMETSAT](../SATELLITE.md)
- [Přehled projektu](../README.md)

## Dashboard

Aplikace automaticky instaluje custom cards a udržuje stabilní Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

Do Resources nepřidávej jednotlivé verzované JavaScript soubory.

Hlavní karta:

```yaml
type: custom:astro-start-card
decision_entity: sensor.astro_vhodnost_foceni
weather_entity: sensor.astro_weather_detail
moon_entity: sensor.mesic_foceni_predpoved
days: 3
```

Satelitní karta:

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: true
```

Měsíční karta:

```yaml
type: custom:moon-forecast-card
entity: sensor.mesic_foceni_predpoved
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
days: 45
```

Pokud po aktualizaci prohlížeč drží starou verzi custom card, proveď jednou `Ctrl+F5`.
