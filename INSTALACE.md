# Instalace Astro Weather do Home Assistant

Tento návod popisuje čistou instalaci aktuální verze **Home Assistant Astro Weather** z GitHub repozitáře.

> **Jazyk a oblast použití:** uživatelské rozhraní i dokumentace jsou zatím pouze česky. Projekt je primárně určen pro observatoře v České republice, protože jedna z hlavních meteorologických větví používá model **ČHMÚ ALADIN**. MET Norway a DWD ICON mají širší pokrytí, ale provoz mimo ČR zatím není hlavní podporovaný scénář.

## 1. Požadavky

- Home Assistant s podporou instalace Apps/Add-ons z vlastního repozitáře.
- Architektura `amd64` nebo `aarch64`.
- Internetové připojení pro meteorologická a satelitní data.
- Správná poloha observatoře: zeměpisná šířka, délka, nadmořská výška a časové pásmo.
- Pro kvantitativní satelitní data EUMETSAT je potřeba bezplatný účet EUMETSAT a API consumer key/secret. Bez nich aplikace funguje dál, pouze nebude dostupná kvantitativní CLM vrstva.

## 2. Přidání GitHub repozitáře do Home Assistant

1. V Home Assistant otevři **Nastavení -> Apps / Doplňky -> Obchod**.
2. Otevři nabídku se třemi tečkami a zvol **Repositories / Repozitáře**.
3. Přidej tento repozitář:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

4. Po načtení repozitáře vyber **Astro Weather Backend**.
5. Aplikaci nainstaluj.

## 3. Základní konfigurace

Před prvním spuštěním nastav skutečnou polohu observatoře, ne polohu domácího Home Assistant serveru, pokud se liší.

Minimálně zkontroluj:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
```

Doporučené základní nastavení pro ČR:

```yaml
refresh_minutes: 30
horizon_hours: 72
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

Úplný popis parametrů je v [KONFIGURACE.md](KONFIGURACE.md).

## 4. EUMETSAT satelit - volitelné, ale doporučené

Bez EUMETSAT přihlašovacích údajů zůstane hlavní předpověď funkční. Pro skutečnou kvantitativní detekci oblačnosti přes MTG/FCI Cloud Mask je potřeba API přístup.

1. Vytvoř nebo použij existující účet v EUMETSAT User Portal.
2. V portálu otevři sekci **API access**.
3. Vygeneruj consumer key a consumer secret.
4. V nastavení Astro Weather vyplň:

```yaml
eumetsat_consumer_key: "TVUJ_CONSUMER_KEY"
eumetsat_consumer_secret: "TVUJ_CONSUMER_SECRET"
```

Secret je v Home Assistant konfiguraci veden jako heslo a aplikace ho nezveřejňuje v senzorech ani v logu.

Podrobnosti o satelitní vrstvě jsou v [SATELLITE.md](SATELLITE.md).

## 5. První spuštění

Po uložení konfigurace aplikaci spusť.

Doporučení:

- zapnout **Start on boot / Spustit při startu**,
- zapnout **Watchdog**,
- automatické aktualizace používat podle vlastního provozního režimu observatoře.

Po startu otevři log aplikace. Měly by se postupně objevit úspěšné aktualizace hlavních zdrojů a publikování Home Assistant entit.

Základní entity:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

Při aktivním EUMETSAT CLM navíc:

```text
sensor.astro_satelit_oblacnost
sensor.astro_model_satelit_shoda
sensor.astro_met_satelit_chyba
sensor.astro_aladin_satelit_chyba
sensor.astro_icon_satelit_chyba
```

## 6. Lovelace resource

Astro Weather si při startu automaticky kopíruje aktuální karty do `/config/www` a udržuje jeden stabilní Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

V **Nastavení -> Dashboardy -> Resources / Zdroje** má být pro Astro Weather pouze tento jeden JavaScript modul.

Pokud automatické přidání resource neproběhne, přidej ručně:

| URL | Typ |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

Nepřidávej jednotlivé soubory `astro-start-card-vXX.js`, `astro-satellite-card-vXX.js` ani `moon-forecast-card-vXX.js` jako samostatné resources. Loader načte správné verze podle manifestu.

## 7. Přidání karet na dashboard

### Hlavní rozhodovací karta

```yaml
type: custom:astro-start-card
decision_entity: sensor.astro_vhodnost_foceni
weather_entity: sensor.astro_weather_detail
moon_entity: sensor.mesic_foceni_predpoved
days: 3
```

Karta zobrazuje tři nejbližší noci, rozhodnutí `SPUSTIT / NEJISTÉ / NESPOUŠTĚT`, modely, kvalitu oblohy, prostorový vývoj oblačnosti, Měsíc a hodinový průběh.

### Satelitní karta

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: true
```

Karta rozlišuje:

- stav CLM **přímo nad observatoří**,
- podíl oblačných CLM vzorků v okolí,
- krátký extrapolační nowcast,
- aktuální IR10.5 snímek EUMETSAT,
- přehrávání přibližně posledních tří hodin IR historie.

### Měsíční karta

```yaml
type: custom:moon-forecast-card
entity: sensor.mesic_foceni_predpoved
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
days: 45
```

## 8. Ověření instalace

Po několika minutách zkontroluj:

1. `sensor.astro_vhodnost_foceni` existuje a není `unavailable`.
2. Hlavní karta se vykreslí bez chyby `Custom element doesn't exist`.
3. V hodinovém přehledu jsou data MET / ALADIN / ICON podle dostupnosti.
4. Interní Měsíc má platná data pro následující noci.
5. Pokud jsou vyplněny EUMETSAT credentials, satelitní karta ukazuje čas CLM a stav observatoře.

## 9. Aktualizace

Aktualizace se instalují standardně přes Home Assistant.

Po aktualizaci aplikace se karty při startu znovu zapíší do `/config/www` a loader začne používat aktuální verzi.

Pokud prohlížeč stále ukazuje starou podobu karty, proveď jednou tvrdé obnovení:

```text
Ctrl+F5
```

Není potřeba ručně měnit Lovelace resource při každé nové verzi.

## 10. Nejčastější problémy

### `Custom element doesn't exist`

Ověř, že v Resources existuje:

```text
/local/astro-weather-cards-loader.js
```

Potom otevři v prohlížeči:

```text
https://TVUJ_HOME_ASSISTANT/local/astro-weather-cards-loader.js
https://TVUJ_HOME_ASSISTANT/local/astro-weather-cards-manifest.json
```

Pokud jsou dostupné, proveď `Ctrl+F5`.

### ALADIN není dostupný

Zkontroluj polohu observatoře a log aplikace. ALADIN je regionální zdroj a právě kvůli němu je projekt primárně zaměřen na ČR.

Výpadek jednoho modelu nemá shodit celý backend; rozhodování pokračuje z dostupných zdrojů s odpovídajícím snížením jistoty.

### Satelit je `unavailable`

Zkontroluj:

- `use_satellite: true`,
- consumer key a consumer secret,
- internetové připojení,
- stáří posledního CLM produktu v logu.

Bez EUMETSAT credentials je nedostupnost kvantitativní CLM vrstvy očekávaná a hlavní meteorologická logika pokračuje dál.

### Karta ukazuje staré hodnoty po aktualizaci

Nejdřív počkej na první celý refresh backendu. Pokud jde pouze o starý vzhled JavaScript karty, použij `Ctrl+F5`.

## Další dokumentace

- [README.md](README.md) - přehled projektu a princip rozhodování
- [KONFIGURACE.md](KONFIGURACE.md) - všechny volby aplikace
- [SATELLITE.md](SATELLITE.md) - EUMETSAT MTG/FCI, CLM, IR a timelapse
