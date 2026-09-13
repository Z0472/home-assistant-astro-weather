# Astro Weather Backend – dokumentace

Astro Weather je Home Assistant App/Add-on pro plánování astrofotografie a pro provozní rozhodnutí, zda má smysl observatoř pro danou noc spouštět.

> **UI a plná dokumentace jsou zatím pouze v češtině.** Projekt je primárně určen pro Českou republiku, protože využívá regionální model ČHMÚ ALADIN CZ 1 km.

## 1. Nejdříve nastavte polohu observatoře

V nastavení aplikace změňte minimálně:

```yaml
latitude: 48.0000
longitude: 14.0000
altitude: 500
timezone: Europe/Prague
```

Použijte skutečnou polohu a nadmořskou výšku observatoře. Tyto hodnoty mají přímý vliv na modelovou předpověď, prostorovou analýzu, astronomickou noc, Měsíc i satelitní CLM vzorkování.

## 2. Doporučené výchozí funkce

Pro běžnou instalaci v ČR doporučujeme ponechat:

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

Podrobný význam všech parametrů je v [KONFIGURACE.md](https://github.com/Z0472/home-assistant-astro-weather/blob/main/KONFIGURACE.md).

## 3. EUMETSAT – registrace a API klíče

Veřejný IR10.5 obraz může fungovat bez API credentials. Pro kvantitativní **MTG/FCI Cloud Mask (CLM)** je však potřeba účet EUMETSAT a dvojice **Consumer key / Consumer secret**.

### Registrace

1. Otevřete EUMETSAT User Portal:

   https://user.eumetsat.int/

2. Pokud účet nemáte, zaregistrujte se a přihlaste.
3. Po přihlášení otevřete API Key Management:

   https://api.eumetsat.int/api-key/

4. V části **User Credentials** zobrazte a zkopírujte:
   - **Consumer key**
   - **Consumer secret**

Do konfigurace aplikace vložte:

```yaml
eumetsat_consumer_key: "VAS_CONSUMER_KEY"
eumetsat_consumer_secret: "VAS_CONSUMER_SECRET"
```

Do aplikace se **nevkládá ručně krátkodobý access token**. Backend jej získává automaticky z Consumer key + Consumer secret a podle potřeby jej obnovuje.

Pokud API vrací `401` nebo `403`, ověřte aktivní účet, správné credentials a případná datová/licenční oprávnění v EUMETSAT User Portal.

Oficiální návody EUMETSAT:

- https://user.eumetsat.int/resources/user-guides/data-store-detailed-guide
- https://user.eumetsat.int/resources/user-guides/introductory-data-store-user-guide
- https://user.eumetsat.int/resources/user-guides/mtg-data-access-guide

## 4. Hlavní entity

Po prvním spuštění by měly vzniknout zejména:

```text
sensor.astro_weather_detail
sensor.astro_vhodnost_foceni
sensor.mesic_foceni_predpoved
```

Při aktivním EUMETSAT CLM také:

```text
sensor.astro_satelit_oblacnost
sensor.astro_model_satelit_shoda
sensor.astro_met_satelit_chyba
sensor.astro_aladin_satelit_chyba
sensor.astro_icon_satelit_chyba
```

## 5. Dashboard resource

Aplikace udržuje jeden stabilní Lovelace resource:

```text
/local/astro-weather-cards-loader.js
```

V **Nastavení → Dashboardy → Zdroje / Resources** má být pro Astro Weather pouze tento jeden resource typu **JavaScript module**.

Jednotlivé verzované soubory `astro-start-card-vXX.js`, `astro-satellite-card-vXX.js` ani `moon-forecast-card-vXX.js` jako samostatné resources nepřidávejte.

## 6. Doporučené karty

### Hlavní rozhodovací karta

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

## 7. Jak číst satelitní kartu

- **Observatoř: jasno / mrak** = středový CLM vzorek přímo nad observatoří.
- **Okolí 30 km: N %** = podíl oblačných CLM vzorků v regionálním 17bodovém vzorkování.
- **TEĎ** = poslední skutečné regionální CLM pozorování.
- **+1 / +2 / +3 h** = extrapolační nowcast trendu okolí, nikoli budoucí satelitní snímky.
- **Shoda modelů se satelitem** se porovnává se středovým CLM vzorkem nad observatoří.
- IR10.5 historie používá EUMETView WMS a cache prohlížeče; plné historické JPEGy se neukládají na disk Home Assistantu.

## 8. Ochrana úložiště

Velké pracovní GRIB/satelitní soubory se zpracovávají v RAM (`/dev/shm`) a po vzorkování se odstraňují. Cílem je omezit opakované zápisy na SD kartu nebo SSD Home Assistantu.

## 9. Po aktualizaci

Pokud po aktualizaci aplikace dashboard stále zobrazuje starou podobu custom card, použijte jednou:

```text
Ctrl+F5
```

Resource URL se při aktualizacích nemění.

## Kompletní návody na GitHubu

- Instalace: https://github.com/Z0472/home-assistant-astro-weather/blob/main/INSTALACE.md
- Konfigurace: https://github.com/Z0472/home-assistant-astro-weather/blob/main/KONFIGURACE.md
- Satelit: https://github.com/Z0472/home-assistant-astro-weather/blob/main/SATELLITE.md
- Přehled projektu: https://github.com/Z0472/home-assistant-astro-weather
