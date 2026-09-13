# EUMETSAT MTG/FCI satelitní vrstva

Satelitní vrstva Astro Weather slouží k porovnání meteorologických modelů s aktuálně pozorovanou oblačností a ke krátkodobému nowcastu.

V současné implementaci **satelit přímo nepřepisuje hlavní verdikt SPUSTIT / NEJISTÉ / NESPOUŠTĚT**. Je to samostatná pozorovací vrstva, která ukazuje, co se děje právě teď nad observatoří a v jejím okolí.

## Použitá data

### MTG/FCI Cloud Mask

Kvantitativní oblačnost používá EUMETSAT MTG/FCI Level-2 Cloud Mask (CLM), GRIB2 kolekci:

```text
EO:EUM:DAT:0800
```

Nový produkt je typicky dostupný v desetiminutovém kroku.

Backend nepočítá oblačnost z odstínu obrázku. Stahuje skutečný CLM produkt a čte jeho kategoriální hodnoty pomocí ecCodes `grib_get`.

### IR10.5 vizualizace

Pro mapový podklad se používá EUMETView WMS vrstva MTG/FCI IR10.5 s výřezem přibližně ±150 km kolem nakonfigurované observatoře.

IR obraz je vizualizace; kvantitativní rozhodování CLM je založené na GRIB Cloud Mask datech, nikoliv na ruční interpretaci jasu IR obrazu.

## Registrace a API credentials

Data Store lze procházet bez registrace, ale stahovací API vyžaduje autentizaci.

### 1. EUMETSAT účet

Zaregistrujte se nebo se přihlaste:

https://user.eumetsat.int/

Pokud účet nemáte, použijte **Register – Create new account**.

### 2. API Key Management

Po přihlášení otevřete:

https://api.eumetsat.int/api-key/

Na stránce **API Key Management** je sekce **User Credentials**, kde jsou:

- Consumer key
- Consumer secret

Hodnoty jsou standardně skryté; zobrazte je a zkopírujte do konfigurace Astro Weather.

```yaml
eumetsat_consumer_key: "VAS_CONSUMER_KEY"
eumetsat_consumer_secret: "VAS_CONSUMER_SECRET"
```

Do konfigurace nevkládejte ručně access token. Backend z key + secret automaticky získá krátkodobý token a podle potřeby jej obnovuje.

Oficiální EUMETSAT dokumentace:

- https://user.eumetsat.int/resources/user-guides/data-store-detailed-guide
- https://user.eumetsat.int/resources/user-guides/introductory-data-store-user-guide
- https://user.eumetsat.int/resources/user-guides/mtg-data-access-guide

Některé EUMETSAT kolekce mohou vyžadovat odpovídající datovou licenci. Pokud API vrací `401` nebo `403`, zkontrolujte účet, API credentials a datová oprávnění v User Portal.

## Konfigurace satelitu

Doporučené výchozí nastavení:

```yaml
use_satellite: true
satellite_radius_km: 30
satellite_refresh_minutes: 10
satellite_entity: sensor.astro_satelit_oblacnost
satellite_comparison_entity: sensor.astro_model_satelit_shoda
eumetsat_consumer_key: "VAS_KEY"
eumetsat_consumer_secret: "VAS_SECRET"
```

`satellite_radius_km` může být 10–50 km. Výchozích 30 km odpovídá prostorovému okolí používanému na kartě.

## 17 CLM vzorků

Backend používá 17 bodů:

- 1× střed – observatoř,
- 8× směr po 45° v polovině radiusu,
- 8× směr po 45° na plném radiusu.

Tím vzniká jednoduchý prostorový obraz oblačnosti bez nutnosti zpracovávat celý satelitní raster pro lokální rozhodnutí.

## Důležité rozlišení: observatoř vs. okolí

Satelitní karta záměrně ukazuje dvě různé informace.

### Observatoř: jasno / mrak

Stav observatoře pochází pouze ze **středového CLM vzorku** přímo nad nakonfigurovanou polohou.

To je lokální odpověď na otázku: „Co detekuje CLM právě nad observatoří?“

### Okolí N km: X % oblačných CLM vzorků

Regionální procento je podíl oblačných bodů ze všech dostupných vzorků v okolí.

Například `53 %` neznamená, že je nad observatoří 53 % oblačnosti. Může nastat například tento stav:

```text
Observatoř: jasno
Okolí 30 km: 53 % oblačných CLM vzorků
```

To je správný výsledek, pokud je středový bod jasný, ale v okolí už je výrazná oblačnost.

## Porovnání modelů se satelitem

`sensor.astro_model_satelit_shoda` porovnává aktuální modelový konsensus v čase CLM se **středovým CLM vzorkem nad observatoří**.

Regionální 30km podíl se do této shody nezapočítává, protože modelová hodnota je vztažena k poloze observatoře.

Na kartě tak může být například:

```text
Aktuálně v čase CLM: 100 % shoda · modelový konsensus 100 % · observatoř mrak
```

nebo naopak nízká shoda, pokud modely předpovídají zataženo a CLM střed je jasný.

## Krátkodobý nowcast

Karta ukazuje:

```text
TEĎ
+1 h
+2 h
+3 h
```

`TEĎ` je skutečný regionální podíl CLM vzorků z posledního pozorování.

`+1 / +2 / +3 h` jsou extrapolované hodnoty odvozené z několika posledních CLM snímků. Nejde o budoucí satelitní měření ani o nový numerický meteorologický model.

Nowcast je určen hlavně k rychlému odhadu, zda se okolí zatahuje nebo vyjasňuje.

## Směr hrany a ETA

Směr a ETA jsou zobrazené konzervativně. Backend nehledá směr z jednoho jediného náhodného vzorku, ale vyžaduje stabilnější chování v několika po sobě jdoucích CLM rámcích.

Pokud je hrana oblačnosti dostatečně konzistentní a přibližuje se, může karta zobrazit přibližný směr a ETA.

## IR timelapse

Satelitní karta umí přehrát přibližně poslední tři hodiny IR10.5 historie.

Používá se 20 časových kroků po 10 minutách. Historický obraz se získává přímo přes EUMETView WMS parametr:

```text
time=<ISO timestamp>
```

### Důležité: obrázky se nearchivují na HA disk

Astro Weather neukládá 20 JPEGů do `/data` ani `/config`.

Historické snímky načítá prohlížeč přímo z EUMETView a používá svou běžnou cache. Tím se minimalizují zápisy na SD kartu/SSD Home Assistantu.

### CLM body během historie

Aktuální CLM body patří k aktuálnímu okamžiku. Při prohlížení staršího IR snímku jsou proto aktuální modré/šedé CLM body skryté, aby nevznikla časově chybná kombinace starého obrazu a nových CLM hodnot.

Žlutý terč observatoře a orientační kruhy zůstávají zobrazené.

Po návratu na živý obraz se aktuální CLM body znovu zobrazí.

## Barvy a overlay

Na aktuálním IR obrazu:

- modrá = CLM jasno,
- šedá = CLM mrak,
- žlutý terč = observatoř,
- kruhy = přibližně R/2 a R, typicky 15 / 30 km.

Body jsou skutečné vzorky použité backendem. Nejde o interpolovanou plochu oblačnosti.

## Publikované entity

### `sensor.astro_satelit_oblacnost`

Obsahuje mimo jiné:

- čas posledního CLM,
- stav středového bodu,
- regionální cloud fraction,
- jednotlivé CLM body,
- trend,
- regionální nowcast,
- případnou hranu a ETA,
- WMS URL a parametry vizualizace.

### `sensor.astro_model_satelit_shoda`

Okamžitá shoda modelového konsensu se středovým CLM vzorkem.

### Chybové senzory jednotlivých modelů

```text
sensor.astro_met_satelit_chyba
sensor.astro_aladin_satelit_chyba
sensor.astro_icon_satelit_chyba
```

Tyto senzory jsou vhodné pro Recorder/statistiky a dlouhodobé porovnání skutečné výkonnosti modelů.

## Dashboard YAML

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: true
```

`show_image: true` zobrazí IR10.5 obraz a historii.

`show_clm_map: true` zobrazí CLM body nad aktuálním obrazem.

## Ochrana RAM a úložiště

Astro Weather je navržen i pro menší Home Assistant hardware.

Velké pracovní soubory se proto nezpracovávají jako trvalý diskový archiv:

- stažený EUMETSAT SIP/ZIP zůstává v paměti,
- extrahovaný velký GRIB se zapisuje pouze do `/dev/shm`,
- po vzorkování se okamžitě maže,
- ALADIN a EUMETSAT sdílejí zámek pro velké RAM scratch soubory,
- pokud není bezpečné RAM scratch prostředí dostupné, zdroj raději selže fail-open místo velkých opakovaných zápisů na SD kartu.

Na trvalém úložišti zůstávají jen malé provozní/cache informace, nikoli plné satelitní obrazové série.

## Fail-open chování

Pokud EUMETSAT credentials chybí nebo satelitní služba dočasně selže:

- hlavní meteorologická předpověď pokračuje,
- hlavní SPUSTIT / NEJISTÉ / NESPOUŠTĚT logika nespadne kvůli satelitu,
- kvantitativní satelitní entity mohou být `unavailable`,
- veřejná IR vizualizace může zůstat dostupná.

To je záměrné: satelit je velmi užitečný doplňkový zdroj, ale jeho krátkodobý výpadek nesmí vyřadit celý weather backend.