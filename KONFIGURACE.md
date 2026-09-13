# Konfigurace Astro Weather

Tato stránka popisuje parametry Home Assistant App **Astro Weather Backend**. Hodnoty uvedené jako výchozí odpovídají aktuálnímu výchozímu nastavení projektu.

## Co je nutné změnit

Po instalaci zkontroluj nebo vyplň minimálně:

| Parametr | Nutné | Význam |
| --- | --- | --- |
| `latitude` | ano | Zeměpisná šířka observatoře v desetinných stupních. |
| `longitude` | ano | Zeměpisná délka observatoře v desetinných stupních. |
| `altitude` | ano | Nadmořská výška observatoře v metrech. |
| `timezone` | zkontrolovat | Pro ČR obvykle `Europe/Prague`. |
| `eumetsat_consumer_key` | pro CLM | EUMETSAT Consumer key pro kvantitativní satelitní data. |
| `eumetsat_consumer_secret` | pro CLM | EUMETSAT Consumer secret. |

Pokud EUMETSAT klíče nevyplníš, veřejný IR obraz může fungovat, ale kvantitativní CLM data nebudou dostupná.

## Lokalita a čas

| Parametr | Výchozí | Rozsah / typ | Popis |
| --- | ---: | --- | --- |
| `latitude` | `50.0755` | `float` | Zeměpisná šířka. Změň na skutečnou polohu observatoře. |
| `longitude` | `14.4378` | `float` | Zeměpisná délka. Změň na skutečnou polohu observatoře. |
| `altitude` | `250` | `int` | Nadmořská výška v metrech. |
| `timezone` | `Europe/Prague` | `string` | Časová zóna pro lokální časy, noc a UI. |

Poloha ovlivňuje modely, astronomickou noc, Měsíc, satelitní CLM i mapový výřez.

## Základní meteorologická předpověď

| Parametr | Výchozí | Rozsah | Popis |
| --- | ---: | ---: | --- |
| `refresh_minutes` | `30` | 10–180 min | Perioda hlavní obnovy meteorologických dat. Satelit má vlastní periodu. |
| `horizon_hours` | `72` | 24–120 h | Délka meteorologického horizontu. |
| `met_user_agent` | `AstroWeatherBackend/...` | string | User-Agent pro MET Norway. Běžně není potřeba měnit. |
| `use_icon` | `true` | bool | Zapne DWD ICON Seamless jako třetí model. |

### Poznámka k modelům

Pro hlavní konsensus se používají dostupné hodnoty z MET, ALADIN a ICON. Pokud jeden zdroj není dostupný, backend může pokračovat s ostatními modely podle své fallback logiky.

ALADIN je zásadní důvod, proč je projekt primárně zaměřený na Českou republiku.

## Rozhodování o focení

| Parametr | Výchozí | Rozsah | Popis |
| --- | ---: | ---: | --- |
| `decision_nights` | `3` | 1–5 | Počet nocí zobrazených/vyhodnocených v hlavní kartě. |
| `min_good_block_hours` | `4.0` | 1–12 h | Minimální délka dobrého souvislého bloku. |
| `max_start_delay_minutes` | `120` | 0–360 min | Jak pozdě po začátku astronomické tmy ještě dává smysl doporučit start focení. |
| `prep_minutes` | `45` | 0–240 min | Rezerva na přípravu/chlazení techniky před doporučeným startem. |
| `good_score` | `70` | 0–100 | Hranice skóre pro dobrý stav. |
| `marginal_score` | `50` | 0–100 | Hranice skóre pro hraniční stav. |
| `disagreement_warn` | `35` | 0–100 p. b. | Rozptyl modelů, od kterého je neshoda významná. |
| `disagreement_bad` | `55` | 0–100 p. b. | Silná neshoda modelů. |
| `wind_warn_ms` | `8.0` | m/s | Varovná hranice větru. |
| `wind_bad_ms` | `12.0` | m/s | Kritická hranice větru. Musí být alespoň stejně vysoká jako `wind_warn_ms`. |

Tyto prahy mají smysl ladit podle konkrétní montáže, střechy, ohniska a požadované kvality dat. Výchozí hodnoty jsou doporučený startovní bod, nikoli univerzální fyzikální norma.

## Měsíc

| Parametr | Výchozí | Rozsah | Popis |
| --- | ---: | ---: | --- |
| `use_moon` | `true` | bool | Zapne interní výpočet Měsíce a jeho vlivu. |
| `moon_entity` | `sensor.mesic_foceni_predpoved` | string | Název publikované entity. |
| `moon_horizon_days` | `45` | 3–60 dní | Počet dní/nocí dopředu pro měsíční přehled. |
| `moon_interference_illumination_pct` | `15.0` | 0–100 % | Prah osvětlení používaný při posuzování rušení Měsícem. |
| `moon_interference_altitude_deg` | `0.0` | −5 až 30° | Prah výšky Měsíce nad horizontem pro posuzování rušení. |

Rozhodování o Měsíci je vztahováno k astronomické noci, nikoliv k celému kalendářnímu dni.

## Prostorová analýza oblačnosti

| Parametr | Výchozí | Rozsah | Popis |
| --- | ---: | ---: | --- |
| `spatial_cloud_analysis` | `true` | bool | Zapne prostorové vyhodnocení okolí observatoře. |
| `spatial_radius_km` | `30` | 10–50 km | Poloměr okolí pro prostorovou analýzu modelové oblačnosti. |

Prostorová vrstva slouží k odhalení situací, kdy je observatoř blízko hrany oblačnosti a jediný bod modelu by byl příliš optimistický nebo pesimistický.

Výchozích **30 km** je rozumný kompromis pro běžné astrofotografické rozhodování.

## Satelit EUMETSAT MTG/FCI

| Parametr | Výchozí | Rozsah / typ | Popis |
| --- | ---: | --- | --- |
| `use_satellite` | `true` | bool | Zapne satelitní integraci. |
| `satellite_radius_km` | `30` | 10–50 km | Poloměr regionálního CLM vzorkování. |
| `satellite_refresh_minutes` | `10` | 10–60 min | Perioda kontroly nových CLM dat. Doporučeno ponechat 10 min. |
| `satellite_entity` | `sensor.astro_satelit_oblacnost` | string | Hlavní satelitní entity. |
| `satellite_comparison_entity` | `sensor.astro_model_satelit_shoda` | string | Entity okamžité shody modelů se satelitem. |
| `eumetsat_consumer_key` | prázdné | string | EUMETSAT Consumer key. |
| `eumetsat_consumer_secret` | prázdné | password | EUMETSAT Consumer secret. |

### Kde získat klíče

1. Registrace/přihlášení: https://user.eumetsat.int/
2. API Key Management: https://api.eumetsat.int/api-key/
3. Zkopíruj **Consumer key** a **Consumer secret** z `User Credentials`.

Nevkládej ručně krátkodobý access token. Backend si jej vytváří sám.

### Význam satelitních hodnot

`center_cloud_pct` / stav observatoře odpovídá středovému CLM vzorku přímo nad observatoří.

`cloud_pct` je regionální podíl oblačných CLM vzorků v okolí. Není to stejné jako procento oblačnosti přímo nad dalekohledem.

Krátký nowcast `+1 / +2 / +3 h` je extrapolace trendu regionálních vzorků, nikoliv budoucí satelitní měření.

## Aerosoly / AOD

| Parametr | Výchozí | Rozsah | Popis |
| --- | ---: | ---: | --- |
| `use_aerosols` | `true` | bool | Zapne CAMS/Open-Meteo AOD. |
| `aerosol_refresh_minutes` | `180` | 60–360 min | Perioda obnovy aerosolových dat. |
| `aod_warn` | `0.30` | 0.11–4.99 | Varovný práh AOD 550. |
| `aod_bad` | `0.40` | 0.12–5.0 | Špatný práh AOD 550; musí být vyšší než `aod_warn`. |

Vyšší AOD obvykle znamená více aerosolu/zákalu a horší transparentnost oblohy.

## Seeing

| Parametr | Výchozí | Rozsah | Popis |
| --- | ---: | ---: | --- |
| `use_seeing` | `true` | bool | Zapne modelový seeing z 7Timer ASTRO. |
| `seeing_warn_arcsec` | `1.8` | 1.0–7.99″ | Varovná hranice seeingu. |
| `seeing_bad_arcsec` | `2.5` | 1.01–8.0″ | Špatná hranice seeingu; musí být vyšší než `seeing_warn_arcsec`. |

Seeing je modelový odhad a má být chápán jako doplňkový indikátor, ne jako přesná lokální okamžitá hodnota.

## Home Assistant entity a instalace karet

| Parametr | Výchozí | Popis |
| --- | ---: | --- |
| `publish_homeassistant_entities` | `true` | Publikuje entity do Home Assistantu. |
| `weather_entity` | `sensor.astro_weather_detail` | Detail počasí. |
| `decision_entity` | `sensor.astro_vhodnost_foceni` | Hlavní rozhodovací entity. |
| `install_dashboard_cards` | `true` | Automaticky kopíruje custom karty do `/config/www`. |
| `install_lovelace_resources` | `true` | Udržuje stabilní Astro Weather Lovelace resource. |

Doporučení: názvy entit neměň, pokud pro to nemáš konkrétní důvod. Dokumentace a příklady předpokládají výchozí názvy.

## Debug

| Parametr | Výchozí | Popis |
| --- | ---: | --- |
| `debug` | `false` | Zapne podrobnější diagnostiku a tracebacky v logu. |

Zapínej jen při řešení problému; běžně jej nech `false`.

## Doporučený minimální blok konfigurace

Pro typickou českou observatoř stačí po instalaci hlavně správně nastavit lokalitu a EUMETSAT credentials:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: "Europe/Prague"

eumetsat_consumer_key: "TVUJ_KEY"
eumetsat_consumer_secret: "TVUJ_SECRET"
```

Ostatní výchozí hodnoty bych při první instalaci neměnila. Nejdřív nech systém několik nocí běžet a až potom upravuj prahy podle skutečných podmínek své observatoře.

## Doporučené pořadí ladění

Pokud chceš systém přizpůsobit konkrétní technice, měň parametry postupně:

1. lokalita a timezone,
2. délka požadovaného dobrého bloku,
3. vítr,
4. AOD a seeing,
5. radius prostorové analýzy,
6. teprve potom skórovací a disagreement prahy.

Neměň několik skupin prahů najednou, jinak bude obtížné poznat, co změnilo verdikt.
