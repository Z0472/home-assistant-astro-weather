# EUMETSAT MTG/FCI satelitní vrstva

Astro Weather používá EUMETSAT MTG/FCI dvěma odlišnými způsoby:

1. **FCI Cloud Mask (CLM)** pro kvantitativní informaci jasno/mrak.
2. **IR10.5 WMS obraz** pro vizuální kontrolu širšího okolí a historický timelapse.

Satelitní vrstva je úmyslně oddělená od dlouhodobého modelového rozhodnutí. Ukazuje skutečnou pozorovanou situaci a krátkodobý trend, ale sama přímo nepřepisuje finální `SPUSTIT / NEJISTÉ / NESPOUŠTĚT`.

## CLM zdroj

Kvantitativní oblačnost používá EUMETSAT MTG/FCI Level-2 Cloud Mask, GRIB-2 kolekci:

```text
EO:EUM:DAT:0800
```

Backend pravidelně hledá poslední produkty a vzorkuje je v okolí observatoře.

Používá se 17 bodů:

- `C` - observatoř,
- 8 směrů ve vzdálenosti R/2,
- 8 směrů ve vzdálenosti R.

Výchozí R je 30 km.

## Co znamenají údaje na satelitní kartě

### Observatoř: jasno / mrak

Toto je **jediný středový CLM vzorek přímo nad zadanou polohou observatoře**.

Je to nejbližší odpověď na otázku „co satelit vidí právě nad dalekohledem“.

### Okolí 30 km: X % oblačných CLM vzorků

To není procento oblačnosti přímo nad observatoří.

Je to podíl oblačných kategorií z platných bodů v 17bodovém vzorku okolí. Například 9 oblačných bodů ze 17 znamená přibližně 53 % regionálního vzorku.

Tato veličina je vhodná pro sledování přibližování nebo ústupu větší oblačné oblasti.

### TEĎ / +1 h / +2 h / +3 h

- `TEĎ` = skutečný poslední regionální CLM podíl.
- `+1 h`, `+2 h`, `+3 h` = krátký **extrapolační nowcast** z posledního trendu.

Budoucí dlaždice nejsou budoucí satelitní měření ani meteorologický model. Jsou to pouze projekce pokračování pozorovaného trendu.

## Porovnání modelů se satelitem

`sensor.astro_model_satelit_shoda` porovnává aktuální dostupný konsensus MET / ALADIN / ICON se **středovým CLM vzorkem nad observatoří**.

Regionální 17bodový podíl se do tohoto porovnání nezapočítává, protože modelová hodnota je také vztažená k lokalitě observatoře.

Tím se nerozmíchávají dva různé prostorové významy:

- lokální model ↔ lokální CLM,
- regionální CLM podíl ↔ regionální trend/nowcast.

## Směr hrany a ETA

Směr blížící se nebo ustupující hrany se neukazuje z jediného snímku.

Backend vyžaduje konzistentní chování několika po sobě jdoucích CLM rámců. Teprve při stabilním směru a měřitelném přibližování se může zobrazit orientační ETA.

Je to záměrně konzervativní, aby karta nereagovala přehnaně na jeden chybný nebo okrajový vzorek.

## IR10.5 obraz

Karta zobrazuje veřejný EUMETView WMS výřez IR10.5 kolem observatoře.

Výchozí vizuální výřez má přibližně:

```text
±150 km od observatoře
```

Obraz je zobrazován ve větším rozlišení karty, než je nativní fyzikální rozlišení družicového kanálu. Jemnější vykreslení tedy neznamená, že vzniká nová informace pod nativním rozlišením produktu.

Na živém obrazu jsou překresleny:

- CLM vzorky,
- kruhy R/2 a R,
- značka observatoře.

Barevná legenda karty:

- modrá = jasno,
- šedá = mrak,
- žlutý terč = observatoř.

## Časy na kartě

Karta záměrně odděluje dva různé časy:

### `CLM HH:mm · před N min`

- `HH:mm` je čas posledního CLM měření,
- `před N min` se přepočítává živě v prohlížeči,
- není potřeba refresh celé stránky.

### `IR obnoveno HH:mm`

Toto je čas, kdy se do karty obnovil WMS obraz. Není to tvrzení, že samotné satelitní měření vzniklo přesně v tuto minutu.

## IR historie a timelapse

Satelitní karta umí přehrát přibližně poslední tři hodiny IR historie.

Výchozí nastavení:

```text
20 rámců
10 minut mezi rámci
```

To odpovídá přibližně 3 hodinám a 10 minutám historie.

Historické snímky se **neukládají na disk Home Assistant**. Karta používá WMS `time=` a jednotlivé obrazy načítá až webový prohlížeč.

Výhody:

- nevzniká archiv JPEGů na SD/SSD,
- backend nemusí vyrábět video,
- zatížení Raspberry Pi / Home Assistant serveru je minimální,
- uživatel může sliderem přejít na libovolný historický rámec.

Během historického přehrávání jsou aktuální modré/šedé CLM body skryté, protože patří pouze k současnému CLM času a nad starším IR snímkem by byly časově zavádějící.

Po návratu na **Živě** se znovu zobrazí aktuální IR obraz i aktuální CLM body.

## EUMETSAT API credentials

Vyhledání dostupných produktů je možné bez přihlášení, ale stažení kvantitativního CLM produktu vyžaduje EUMETSAT API consumer key a secret.

V Home Assistant konfiguraci:

```yaml
use_satellite: true
satellite_radius_km: 30
satellite_refresh_minutes: 10
eumetsat_consumer_key: "TVUJ_CONSUMER_KEY"
eumetsat_consumer_secret: "TVUJ_CONSUMER_SECRET"
```

Backend z key/secret získává krátkodobý access token automaticky.

Pokud credentials chybí nebo EUMETSAT není dostupný:

- hlavní modelové rozhodování pokračuje,
- kvantitativní CLM entita je `unavailable`,
- satelitní výpadek nesmí shodit celý backend.

## Publikované entity

```text
sensor.astro_satelit_oblacnost
sensor.astro_model_satelit_shoda
sensor.astro_met_satelit_chyba
sensor.astro_aladin_satelit_chyba
sensor.astro_icon_satelit_chyba
```

### `sensor.astro_satelit_oblacnost`

Obsahuje mimo jiné:

- čas CLM,
- středový stav nad observatoří,
- regionální podíl oblačných vzorků,
- 17 CLM bodů,
- trend,
- krátký nowcast,
- případnou stabilní hranu a ETA,
- URL vizuálního IR výřezu.

### `sensor.astro_model_satelit_shoda`

Obsahuje aktuální porovnání modelového konsensu se středovým CLM stavem nad observatoří.

### Chybové senzory jednotlivých modelů

MET / ALADIN / ICON error senzory jsou určené hlavně pro dlouhodobé Home Assistant Recorder/statistiky. Smyslem je hodnotit modely za mnoho situací, ne podle jednoho náhodného večera.

## Ochrana SD/SSD a RAM

Astro Weather je navržen i pro nepřetržitý provoz na menších Home Assistant zařízeních.

Velké dočasné soubory se proto zpracovávají takto:

- stažený EUMETSAT balíček se drží v paměti,
- velký rozbalený CLM GRIB se zapisuje pouze do `/dev/shm`,
- po vzorkování se okamžitě odstraní,
- ALADIN používá stejný princip pro dočasný rozbalený GRIB,
- velké GRIB operace jsou vzájemně koordinované,
- CLM se vzorkuje přímým indexem místo paměťově náročného plošného vyhledávání,
- na disk se ukládá pouze malý JSON s několika posledními CLM vzorky potřebnými pro trend.

Pokud není bezpečný RAM scratch k dispozici, satelitní zdroj má raději selhat jako `unavailable`, než začít pravidelně zapisovat velké dočasné soubory na SD kartu.

IR timelapse je čistě browser-side a na Home Assistant disk nezapisuje historické obrazy.

## Dashboard YAML

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: true
```

`show_image: true` je potřeba pro IR obraz a jeho historii.

Podrobná instalace je v [INSTALACE.md](INSTALACE.md).
