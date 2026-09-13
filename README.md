# Home Assistant Astro Weather

![Tests](https://github.com/Z0472/home-assistant-astro-weather/actions/workflows/tests.yml/badge.svg)

**Astro Weather** je Home Assistant App/Add-on pro plánování astrofotografie. Z několika nezávislých meteorologických, astronomických a satelitních zdrojů vytváří jeden provozní výsledek:

**SPUSTIT / NEJISTÉ / NESPOUŠTĚT**

Cílem není nahradit profesionální meteorologii, ale odstranit nutnost před každou nocí ručně porovnávat několik modelů, Měsíc, seeing, aerosoly a aktuální satelitní situaci.

> **Jazyk a oblast použití:** UI i dokumentace jsou zatím pouze česky. Projekt je primárně určen pro observatoře v **České republice**, protože jedna z hlavních modelových větví používá regionální data **ČHMÚ ALADIN**. MET Norway a DWD ICON mají širší pokrytí, ale provoz mimo ČR zatím není hlavní podporovaný scénář.

## Dokumentace

- **[INSTALACE.md](INSTALACE.md)** - instalace do Home Assistant krok za krokem
- **[KONFIGURACE.md](KONFIGURACE.md)** - všechny volby aplikace a doporučené hodnoty
- **[SATELLITE.md](SATELLITE.md)** - EUMETSAT MTG/FCI, CLM, IR snímky a timelapse

Tato dokumentace popisuje **současný stav projektu jako výchozí bod**. README není seznam změn proti starším verzím.

## Co Astro Weather používá

### Meteorologické modely

- **MET Norway Locationforecast** - bodová předpověď, oblačnost a její vrstvy, srážky, teplota, rosný bod a vítr.
- **ČHMÚ ALADIN** - regionální model s nativními GRIB daty oblačnosti pro ČR.
- **DWD ICON Seamless přes Open-Meteo** - třetí nezávislý model a zdroj pro část prostorové analýzy.

Modely se neberou jako jednoduchý průměr za všech okolností. Backend sleduje jejich rozptyl, dostupnost a shodu. `Shoda modelů` znamená vzájemnou konzistenci modelů, **nikoli pravděpodobnost, že se předpověď splní**.

### Astronomická noc a Měsíc

Měsíc se počítá interně. Backend zná:

- začátek a konec astronomické noci,
- fázi a osvětlení Měsíce,
- výšku Měsíce,
- východ a západ,
- dobu, kdy Měsíc skutečně ruší astronomickou tmu.

Rozhodnutí o focení se vztahuje k **astronomické noci**, i když hodinový přehled kvůli praktickému plánování zobrazuje také soumrak a svítání.

### Kvalita oblohy

- **CAMS / Open-Meteo Air Quality** - AOD 550 pro průzračnost a informační prach.
- **7Timer ASTRO** - modelový odhad seeingu.

### EUMETSAT MTG/FCI

Satelitní část má dvě role:

1. **CLM Cloud Mask** - skutečná kategorizace jasno/mrak nad observatoří a v jejím okolí.
2. **IR10.5 obraz** - vizuální kontrola pohybu oblačnosti v širším okolí.

Satelitní karta rozlišuje stav přímo nad observatoří od regionálního podílu oblačných vzorků. Obsahuje také krátký extrapolační nowcast a přehrávání přibližně posledních tří hodin IR historie.

Satelit je v současné rozhodovací architektuře **pozorovací kontrola a nowcast**. Samotný satelitní údaj přímo nepřepisuje finální verdikt `SPUSTIT / NEJISTÉ / NESPOUŠTĚT`.

Podrobnosti jsou v [SATELLITE.md](SATELLITE.md).

## Prostorová analýza oblačnosti

Bodová předpověď může být problematická v situaci, kdy model posune hranu oblačnosti o několik kilometrů. Proto Astro Weather vedle bodu observatoře sleduje i okolí.

Standardně se používá **17 vzorkovacích bodů**:

- observatoř,
- 8 směrů v polovině nastaveného poloměru,
- 8 směrů na plném poloměru.

Z toho se odvozuje například:

- stabilita oblačnosti v okolí,
- zda je lokalita poblíž hrany oblačnosti,
- přibližný směr a vzdálenost hrany,
- trend zatahování nebo vyjasňování,
- orientační čas významné změny.

Tato vrstva je úmyslně konzervativní. Může snížit jistotu výsledku, pokud je lokalita na hraně nebo se modely prostorově rozcházejí.

## Jak vzniká rozhodnutí

Backend kombinuje několik typů informace:

- modelový konsensus MET / ALADIN / ICON,
- průběh oblačnosti během astronomické noci,
- prostorovou stabilitu okolí,
- srážky, mlhu a vítr,
- rušení Měsícem,
- AOD,
- seeing.

Výsledkem pro každou noc je:

- verdikt `SPUSTIT`, `NEJISTÉ` nebo `NESPOUŠTĚT`,
- vysvětlení důvodu,
- doporučený souvislý blok,
- vhodný čas přípravy a startu,
- hodinový přehled od večera do rána.

Noční průměry modelů jsou časově vážené podle skutečného překryvu s astronomickou nocí; necelá okrajová hodina nemá stejnou váhu jako celá hodina.

## Home Assistant entity

Základní entity:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

Při aktivním EUMETSAT CLM:

```text
sensor.astro_satelit_oblacnost
sensor.astro_model_satelit_shoda
sensor.astro_met_satelit_chyba
sensor.astro_aladin_satelit_chyba
sensor.astro_icon_satelit_chyba
```

## Dashboard

Aplikace dodává tři hlavní custom cards:

- `custom:astro-start-card` - centrální rozhodnutí a detail noci,
- `custom:astro-satellite-card` - aktuální satelit, CLM okolí, nowcast a IR historie,
- `custom:moon-forecast-card` - delší výhled Měsíce a vhodnosti nocí.

JavaScript karty se instalují do `/config/www`, ale Lovelace používá pouze jeden stabilní loader:

```text
/local/astro-weather-cards-loader.js
```

Jednotlivé verzované `.js` soubory se do Resources ručně nepřidávají.

Přesný postup a YAML příklady jsou v [INSTALACE.md](INSTALACE.md).

## Rychlá instalace

Repozitář pro Home Assistant:

```text
https://github.com/Z0472/home-assistant-astro-weather
```

Po instalaci je nutné nastavit především skutečnou polohu observatoře:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
```

Pro kvantitativní satelitní CLM vrstvu doplň EUMETSAT consumer key a consumer secret. Bez nich hlavní meteorologická předpověď a rozhodování fungují dál.

Celý postup: **[INSTALACE.md](INSTALACE.md)**.

## Odolnost při výpadku zdrojů

Astro Weather je navržen tak, aby výpadek doplňkového zdroje pokud možno neshodil celý backend.

- Pokud chybí jeden meteorologický model, použijí se dostupné modely a sníží se jistota.
- Pokud není dostupný AOD nebo seeing, základní meteorologická předpověď pokračuje.
- Pokud nejsou dostupné EUMETSAT credentials nebo CLM data, satelitní kvantitativní vrstva je `unavailable`, ale finální modelové rozhodnutí pokračuje.

**SkyAccuracy.cz se nepoužívá.**

## Ochrana úložiště Home Assistant

Aplikace počítá s nepřetržitým provozem i na malých Home Assistant systémech.

Velké dočasné GRIB soubory pro satelit a ALADIN se zpracovávají v RAM (`/dev/shm`) a po vzorkování se odstraňují. IR timelapse se nestahuje jako archiv JPEGů na disk Home Assistant; historické WMS snímky načítá až prohlížeč.

## Vývoj a testy

Každá změna v `main` prochází GitHub Actions:

- kompilace Python modulů,
- kontrola syntaxe JavaScript karet,
- regresní testy modelů, rozhodování, Měsíce, prostorové vrstvy a satelitu,
- test release wiring,
- Docker build Home Assistant aplikace.

Projekt je vyvíjen především podle reálného provozu observatoře a praktického rozhodnutí, zda má danou noc smysl techniku spouštět a chladit.
