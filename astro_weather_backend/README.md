# Astro Weather Backend

Home Assistant App/Add-on pro provozní rozhodování, zda má smysl danou noc spustit a chladit astrofotografickou techniku.

Backend kombinuje:

- **MET Norway Locationforecast**,
- **ČHMÚ ALADIN CZ 1 km**,
- **DWD ICON Seamless / Open-Meteo**,
- prostorovou analýzu oblačnosti kolem observatoře,
- interní výpočet astronomické noci a Měsíce,
- **CAMS / Open-Meteo AOD 550**,
- **7Timer ASTRO seeing**,
- **EUMETSAT MTG/FCI Cloud Mask (CLM)** a IR10.5.

Výsledkem je jeden hlavní provozní verdikt:

**SPUSTIT / NEJISTÉ / NESPOUŠTĚT**

> **Jazyk a oblast použití**
>
> Uživatelské rozhraní a plná dokumentace jsou zatím pouze v češtině. Projekt je primárně určen a testován pro Českou republiku, protože jedním z hlavních modelů je ČHMÚ ALADIN CZ 1 km. Stručný anglický popis projektu je v hlavním [README](../README.md#english-summary).

## Co je nutné nastavit

Po instalaci nastavte skutečnou polohu observatoře:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
```

Souřadnice a nadmořská výška ovlivňují bodovou předpověď, prostorové vzorkování, astronomickou noc, Měsíc i satelitní CLM.

Pro kvantitativní EUMETSAT MTG/FCI Cloud Mask vyplňte také:

```yaml
eumetsat_consumer_key: "VAS_CONSUMER_KEY"
eumetsat_consumer_secret: "VAS_CONSUMER_SECRET"
```

EUMETSAT účet vytvoříte na:

https://user.eumetsat.int/

Po přihlášení najdete **Consumer key** a **Consumer secret** v API Key Management:

https://api.eumetsat.int/api-key/

Do aplikace se nevkládá krátkodobý access token; backend si jej z key + secret vytváří automaticky.

## Hlavní entity

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
sensor.astro_satelit_oblacnost
sensor.astro_model_satelit_shoda
```

## Dashboard

Aplikace automaticky instaluje aktuální custom cards a udržuje jediný stabilní Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

Jednotlivé verzované JavaScript soubory karet do Resources ručně nepřidávejte.

### Hlavní karta

```yaml
type: custom:astro-start-card
decision_entity: sensor.astro_vhodnost_foceni
weather_entity: sensor.astro_weather_detail
moon_entity: sensor.mesic_foceni_predpoved
days: 3
```

### Satelitní karta

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: true
```

### Měsíční výhled

```yaml
type: custom:moon-forecast-card
entity: sensor.mesic_foceni_predpoved
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
days: 45
```

## Kompletní dokumentace

- [Instalace krok za krokem](../INSTALACE.md)
- [Přehled všech parametrů](../KONFIGURACE.md)
- [EUMETSAT MTG/FCI a satelitní vrstva](../SATELLITE.md)
- [Přehled projektu](../README.md)

Po aktualizaci použijte jednou `Ctrl+F5`, pokud prohlížeč stále zobrazuje starou verzi custom card.