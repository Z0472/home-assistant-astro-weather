# Konfigurace Astro Weather

Tento soubor popisuje aktuální volby aplikace **Astro Weather Backend**. Dokumentace popisuje současný stav projektu; není to přehled změn mezi verzemi.

## Poloha a čas

| Parametr | Výchozí hodnota | Rozsah / význam |
| --- | ---: | --- |
| `latitude` | `50.0755` | Zeměpisná šířka observatoře. Použij skutečnou polohu dalekohledu. |
| `longitude` | `14.4378` | Zeměpisná délka observatoře. |
| `altitude` | `250` | Nadmořská výška v metrech. |
| `timezone` | `Europe/Prague` | Časové pásmo pro lokální časy v kartách a astronomických výpočtech. |
| `refresh_minutes` | `30` | Obnova hlavní meteorologické předpovědi, 10–180 minut. |
| `horizon_hours` | `72` | Délka předpovědi, 24–120 hodin. |

## Hlavní rozhodnutí

| Parametr | Výchozí hodnota | Význam |
| --- | ---: | --- |
| `decision_nights` | `3` | Počet nocí zpracovaných pro rozhodovací kartu, 1–5. |
| `min_good_block_hours` | `4.0` | Minimální délka souvislého kvalitního bloku pro focení. |
| `max_start_delay_minutes` | `120` | Jak pozdě po začátku astronomické noci ještě může začít doporučený blok. |
| `prep_minutes` | `45` | Rezerva na přípravu observatoře před plánovaným startem. |
| `good_score` | `70` | Hranice skóre pro kvalitní hodinu. |
| `marginal_score` | `50` | Hranice mezi hraniční a špatnou hodinou. |
| `disagreement_warn` | `35` | Rozptyl modelů v procentních bodech, od kterého se bere neshoda vážně. |
| `disagreement_bad` | `55` | Silná neshoda modelů. |
| `wind_warn_ms` | `8.0` | Varovná rychlost větru v m/s. |
| `wind_bad_ms` | `12.0` | Špatná rychlost větru v m/s. |

`Shoda modelů` není pravděpodobnost správné předpovědi. Vyjadřuje, jak podobně v daném čase hodnotí oblačnost dostupné modely.

Noční průměry modelů jsou počítány pro skutečný překryv s astronomickou nocí; okrajové necelé hodiny nemají stejnou váhu jako celá hodina.

## Meteorologické modely

### MET Norway

MET Norway Locationforecast je základní bodový zdroj pro počasí, vrstvy oblačnosti, srážky, teplotu, rosný bod a vítr.

```yaml
met_user_agent: "AstroWeatherBackend/... https://github.com/Z0472/home-assistant-astro-weather"
```

`met_user_agent` ponech standardně beze změny, pokud k tomu nemáš konkrétní důvod.

### ČHMÚ ALADIN

ALADIN používá nativní regionální GRIB data a je jedním z hlavních důvodů, proč je projekt zatím zaměřen především na Českou republiku.

ALADIN nemá samostatný přepínač; backend ho použije, pokud jsou data pro zadanou lokalitu dostupná a validní.

### DWD ICON

```yaml
use_icon: true
```

DWD ICON je třetí nezávislý model v konsensu a současně zdroj pro část prostorové analýzy oblačnosti.

## Prostorová analýza oblačnosti

```yaml
spatial_cloud_analysis: true
spatial_radius_km: 30
```

| Parametr | Výchozí hodnota | Rozsah / význam |
| --- | ---: | --- |
| `spatial_cloud_analysis` | `true` | Zapíná prostorovou analýzu okolí observatoře. |
| `spatial_radius_km` | `30` | Poloměr okolí, 10–50 km. |

Vzorkuje se 17 míst:

- střed = observatoř,
- 8 směrů ve vzdálenosti R/2,
- 8 směrů ve vzdálenosti R.

Cílem není vytvořit další mapu počasí, ale zjistit, zda je observatoř uvnitř stabilně jasné/zatažené oblasti nebo poblíž hrany oblačnosti, která může být modelově posunuta o několik kilometrů.

Prostorová vrstva je konzervativní: může snížit jistotu rozhodnutí, ale nemá sama přepsat tvrdý zákaz na `SPUSTIT`.

## Měsíc

```yaml
use_moon: true
moon_entity: sensor.mesic_foceni_predpoved
moon_horizon_days: 45
moon_interference_illumination_pct: 15.0
moon_interference_altitude_deg: 0.0
```

| Parametr | Výchozí hodnota | Rozsah / význam |
| --- | ---: | --- |
| `use_moon` | `true` | Zapíná interní astronomický výpočet Měsíce. |
| `moon_entity` | `sensor.mesic_foceni_predpoved` | Název publikované entity. |
| `moon_horizon_days` | `45` | Počet dní dopředu, 3–60. |
| `moon_interference_illumination_pct` | `15.0` | Od jakého osvětlení se může Měsíc považovat za rušivý. |
| `moon_interference_altitude_deg` | `0.0` | Minimální výška Měsíce pro rušení, -5 až 30°. |

Rozhodování o rušení Měsíce je vztažené k **astronomické noci**, nikoli k celé době od západu do východu Slunce.

## Aerosoly / průzračnost

```yaml
use_aerosols: true
aerosol_refresh_minutes: 180
aod_warn: 0.30
aod_bad: 0.40
```

Zdroj: CAMS přes Open-Meteo Air Quality.

| Parametr | Výchozí hodnota | Význam |
| --- | ---: | --- |
| `use_aerosols` | `true` | Zapíná AOD 550. |
| `aerosol_refresh_minutes` | `180` | Perioda obnovy 60–360 min. |
| `aod_warn` | `0.30` | Prah pro výrazné zhoršení kvality. |
| `aod_bad` | `0.40` | Prah pro špatnou kvalitu. Musí být vyšší než `aod_warn`. |

Prachová koncentrace je informační; hlavní veličinou pro průzračnost je AOD.

## Seeing

```yaml
use_seeing: true
seeing_warn_arcsec: 1.8
seeing_bad_arcsec: 2.5
```

Zdroj: 7Timer ASTRO.

| Parametr | Výchozí hodnota | Význam |
| --- | ---: | --- |
| `use_seeing` | `true` | Zapíná odhad seeingu. |
| `seeing_warn_arcsec` | `1.8` | Varovný seeing v obloukových sekundách. |
| `seeing_bad_arcsec` | `2.5` | Špatný seeing. Musí být vyšší než varovný práh. |

Seeing je modelový odhad, ne lokální měření FWHM z kamery.

## EUMETSAT MTG/FCI satelit

```yaml
use_satellite: true
satellite_radius_km: 30
satellite_refresh_minutes: 10
satellite_entity: sensor.astro_satelit_oblacnost
satellite_comparison_entity: sensor.astro_model_satelit_shoda
eumetsat_consumer_key: ""
eumetsat_consumer_secret: ""
```

| Parametr | Výchozí hodnota | Rozsah / význam |
| --- | ---: | --- |
| `use_satellite` | `true` | Zapíná satelitní vrstvu. |
| `satellite_radius_km` | `30` | Poloměr CLM vzorkování, 10–50 km. |
| `satellite_refresh_minutes` | `10` | Kontrola nového CLM, 10–60 min. |
| `satellite_entity` | `sensor.astro_satelit_oblacnost` | Hlavní satelitní entita. |
| `satellite_comparison_entity` | `sensor.astro_model_satelit_shoda` | Porovnání aktuálního modelového konsensu se satelitní realitou nad observatoří. |
| `eumetsat_consumer_key` | prázdné | EUMETSAT API consumer key. |
| `eumetsat_consumer_secret` | prázdné | EUMETSAT API consumer secret; Home Assistant ho vede jako password. |

Důležité rozlišení:

- **Observatoř: jasno/mrak** = jediný CLM vzorek přímo nad lokalitou.
- **Okolí N km: X %** = podíl oblačných vzorků z 17 bodů v okolí.
- `TEĎ / +1 / +2 / +3 h` = regionální krátkodobý extrapolační nowcast, nikoli budoucí satelitní měření.
- `Satelit vs aktuální modely` porovnává modelový konsensus se středovým CLM vzorkem nad observatoří.

Satelitní pozorování je v současné logice **pozorovací kontrola a nowcast**. Samo přímo nepřepisuje finální verdikt `SPUSTIT / NEJISTÉ / NESPOUŠTĚT`.

Více v [SATELLITE.md](SATELLITE.md).

## Home Assistant entity názvy

```yaml
publish_homeassistant_entities: true
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
moon_entity: sensor.mesic_foceni_predpoved
satellite_entity: sensor.astro_satelit_oblacnost
satellite_comparison_entity: sensor.astro_model_satelit_shoda
```

Názvy lze změnit, ale pokud je změníš, musí stejné entity používat i konfigurace Lovelace karet.

## Dashboard karty a resources

```yaml
install_dashboard_cards: true
install_lovelace_resources: true
```

Doporučené je ponechat obě hodnoty `true`.

Aplikace pak:

1. zapisuje aktuální JavaScript karty do `/config/www`,
2. zapisuje manifest s aktuálními verzemi,
3. udržuje stabilní loader `/local/astro-weather-cards-loader.js`,
4. pokouší se udržet Lovelace resource automaticky.

Ručně se nepřidávají jednotlivé verzované JS soubory.

## Debug

```yaml
debug: false
```

Zapni pouze při diagnostice. Běžný provoz má zůstat na `false`, aby log nebyl zbytečně hlučný.

## Doporučená výchozí konfigurace pro observatoř v ČR

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
refresh_minutes: 30
horizon_hours: 72
use_moon: true
use_icon: true
use_aerosols: true
use_seeing: true
spatial_cloud_analysis: true
spatial_radius_km: 30
use_satellite: true
satellite_radius_km: 30
satellite_refresh_minutes: 10
moon_horizon_days: 45
moon_interference_illumination_pct: 15.0
moon_interference_altitude_deg: 0.0
min_good_block_hours: 4.0
max_start_delay_minutes: 120
prep_minutes: 45
wind_warn_ms: 8.0
wind_bad_ms: 12.0
aod_warn: 0.30
aod_bad: 0.40
seeing_warn_arcsec: 1.8
seeing_bad_arcsec: 2.5
publish_homeassistant_entities: true
install_dashboard_cards: true
install_lovelace_resources: true
debug: false
```

Hodnoty `latitude`, `longitude` a `altitude` v ukázce jsou pouze příklad. Nahraď je skutečnou polohou observatoře.
