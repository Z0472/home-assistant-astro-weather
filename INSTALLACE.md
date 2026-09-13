# Instalace Astro Weather do Home Assistantu

Tento návod popisuje čistou instalaci Astro Weather jako výchozí stav projektu. Neřeší migraci ze starších verzí.

Uživatelské rozhraní a dokumentace jsou zatím pouze **v češtině**. Projekt je primárně určen pro Českou republiku, protože používá mimo jiné **ČHMÚ ALADIN CZ 1 km**.

## 1. Požadavky

Potřebuješ Home Assistant s podporou Apps/add-ons a jednu z podporovaných architektur:

```text
amd64
aarch64
```

Home Assistant musí mít přístup k internetu pro načítání meteorologických a satelitních dat.

## 2. Přidání GitHub repozitáře

V Home Assistantu otevři správu aplikací:

1. **Nastavení → Aplikace / Apps**.
2. Otevři instalaci / obchod aplikací.
3. V nabídce `⋮` otevři **Repositories / Repozitáře**.
4. Přidej:

   ```text
   https://github.com/Z0472/home-assistant-astro-weather
   ```

5. V seznamu aplikací se objeví **Astro Weather Backend**.
6. Aplikaci nainstaluj.

## 3. Co je nutné nastavit před prvním spuštěním

### Povinné pro správnou lokalitu

V konfiguraci aplikace změň minimálně:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: "Europe/Prague"
```

Použij skutečné hodnoty své observatoře.

- `latitude` – zeměpisná šířka v desetinných stupních.
- `longitude` – zeměpisná délka v desetinných stupních.
- `altitude` – nadmořská výška v metrech.
- `timezone` – pro ČR obvykle ponech `Europe/Prague`.

Souřadnice mají přímý vliv na:

- bodovou předpověď,
- ALADIN/ICON prostorové vzorkování,
- astronomickou noc,
- polohu a rušení Měsíce,
- satelitní CLM vzorky a mapový výřez.

Proto neponechávej demonstrační výchozí souřadnice, pokud neodpovídají tvému místu.

## 4. EUMETSAT – registrace a API klíče

### Kdy jsou klíče potřeba

Bez EUMETSAT klíčů může karta používat veřejný EUMETView IR obraz, ale nebude mít plnohodnotná kvantitativní data **MTG/FCI Cloud Mask (CLM)**.

Pro CLM nastav:

```yaml
eumetsat_consumer_key: "..."
eumetsat_consumer_secret: "..."
```

### Registrace účtu

1. Otevři EUMETSAT User Portal:

   https://user.eumetsat.int/

2. Pokud účet nemáš, zvol **Register – Create new account**.
3. Dokonči registraci a přihlas se.

Oficiální EUMETSAT dokumentace potvrzuje, že pro stahovací API je potřeba registrovaný účet a dočasný access token generovaný z osobních API credentials.

### Kde najít Consumer key a Consumer secret

Po přihlášení otevři přímo:

https://api.eumetsat.int/api-key/

Případně v Data Store / Data Services klikni na své uživatelské jméno a vyber **API Key**.

Na stránce **API Key Management** najdeš v části **User Credentials**:

- **Consumer key**
- **Consumer secret**

Klíče jsou standardně skryté; použij funkci pro zobrazení skrytých klíčů.

Do Home Assistantu vlož:

```yaml
eumetsat_consumer_key: "TVUJ_CONSUMER_KEY"
eumetsat_consumer_secret: "TVUJ_CONSUMER_SECRET"
```

### Nevkládej access token

Do Astro Weather se nevkládá ručně generovaný krátkodobý token. Backend si access token vytváří automaticky z `Consumer key` + `Consumer secret` a podle potřeby jej obnovuje.

EUMETSAT popisuje API Key Management zde:

- https://user.eumetsat.int/resources/user-guides/data-store-detailed-guide
- https://user.eumetsat.int/resources/user-guides/introductory-data-store-user-guide

### Licence a chyba 401/403

EUMETSAT umožňuje data procházet i bez registrace, ale stahování vyžaduje autentizaci. Některé kolekce mohou navíc vyžadovat odpovídající datovou licenci.

Pokud backend po správném zadání key/secret hlásí `401` nebo `403`:

1. ověř, že je účet aktivní,
2. znovu se přihlas do User Portal,
3. otevři API Key Management a ověř key/secret,
4. zkontroluj v User Portal sekci datových licencí, zda má účet oprávnění pro požadovaný produkt,
5. po změně licence se odhlas a znovu přihlas; aktivace oprávnění nemusí být okamžitá.

`eumetsat_consumer_secret` je v Home Assistant konfiguraci veden jako heslo a backend jej nevystavuje v senzorových atributech.

## 5. Doporučené výchozí nastavení pro ČR

Pro běžnou instalaci doporučuji začít s výchozími hodnotami projektu a změnit pouze lokalitu a EUMETSAT credentials:

```yaml
timezone: "Europe/Prague"
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
```

Podrobné vysvětlení všech parametrů je v [KONFIGURACE.md](KONFIGURACE.md).

## 6. První spuštění

Po uložení konfigurace aplikaci spusť.

V logu by se postupně měly objevit úspěšné načtené zdroje:

- MET,
- ALADIN,
- ICON,
- interní Měsíc,
- aerosoly / AOD,
- seeing,
- prostorová analýza,
- EUMETSAT CLM, pokud jsou zadané credentials.

Po prvním spuštění může několik desítek sekund až minut trvat, než se vytvoří všechny Home Assistant entity a zkopírují dashboard karty.

## 7. Entity, které mají vzniknout

Základ:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

Satelit:

```text
sensor.astro_satelit_oblacnost
sensor.astro_model_satelit_shoda
sensor.astro_met_satelit_chyba
sensor.astro_aladin_satelit_chyba
sensor.astro_icon_satelit_chyba
```

Pokud základní entity nevzniknou, nejprve zkontroluj log aplikace.

## 8. Lovelace resources

Astro Weather si kopíruje aktuální karty do `/config/www` a používá stabilní loader:

```text
/local/astro-weather-cards-loader.js
```

V **Nastavení → Dashboardy → Zdroje / Resources** má být pouze jeden Astro Weather resource:

| URL | Typ |
| --- | --- |
| `/local/astro-weather-cards-loader.js` | JavaScript module |

Nepřidávej ručně jednotlivé `astro-start-card-vXX.js` nebo `astro-satellite-card-vXX.js`. Loader a manifest se starají o aktuální verzi automaticky.

## 9. Přidání karet na dashboard

### Hlavní rozhodnutí

```yaml
type: custom:astro-start-card
decision_entity: sensor.astro_vhodnost_foceni
weather_entity: sensor.astro_weather_detail
moon_entity: sensor.mesic_foceni_predpoved
days: 3
```

### Satelit

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: true
```

### Měsíc

```yaml
type: custom:moon-forecast-card
entity: sensor.mesic_foceni_predpoved
weather_entity: sensor.astro_weather_detail
decision_entity: sensor.astro_vhodnost_foceni
days: 45
```

Rozložení karet je na uživateli. Satelitní karta se hodí například do užšího pravého sloupce vedle hlavního rozhodnutí.

## 10. Co udělat po aktualizaci

Po instalaci nové verze:

1. nech aplikaci přepsat aktuální soubory do `/config/www`,
2. otevři dashboard,
3. pokud prohlížeč drží starou custom kartu, použij `Ctrl+F5`.

Není potřeba měnit Lovelace resource URL, protože zůstává:

```text
/local/astro-weather-cards-loader.js
```

## 11. Kontrola funkce satelitu

Na satelitní kartě sleduj:

- `CLM HH:mm · před N min` – čas a živě přepočítávané stáří posledního CLM,
- `Observatoř: jasno / mrak` – středový CLM vzorek,
- `Okolí 30 km: ... %` – regionální vzorkování,
- IR10.5 obraz,
- modré/šedé CLM body,
- shodu modelů se satelitem,
- historii IR snímků přes tlačítko přehrávání a slider.

Pokud vidíš IR obraz, ale CLM je nedostupné, nejčastější příčinou jsou chybějící nebo neplatné EUMETSAT credentials.

## 12. Důležité provozní poznámky

- Astro Weather není bezpečnostní systém pro ochranu střechy nebo techniky.
- Pro déšť, silný vítr a havarijní stavy používej samostatná bezpečnostní pravidla.
- Satelitní obraz a modely jsou podpůrné zdroje pro rozhodnutí o focení.
- Velké pracovní GRIB/satelitní soubory se zpracovávají v RAM, aby se omezily zápisy na úložiště Home Assistantu.
- Historické IR snímky pro timelapse se nestahují do trvalého archivu na HA disk; karta používá EUMETView WMS a cache prohlížeče.

## 13. Když něco nefunguje

### `Custom element doesn't exist`

Ověř:

```text
https://TVUJ-HA/local/astro-weather-cards-loader.js
https://TVUJ-HA/local/astro-weather-cards-manifest.json
```

Potom zkontroluj resource a použij `Ctrl+F5`.

### ALADIN není dostupný

Projekt je primárně určen pro ČR. Pokud je místo mimo podporovanou oblast ALADINu, backend může pokračovat s dostupnými modely, ale výsledky už nejsou v hlavním cílovém scénáři projektu.

### Satelitní CLM není dostupné

Ověř `use_satellite`, key/secret, EUMETSAT účet a případná licenční oprávnění.

### AOD nebo seeing nefunguje

Tyto zdroje jsou doplňkové. Jejich výpadek nemá shodit celý základní meteorologický backend.
