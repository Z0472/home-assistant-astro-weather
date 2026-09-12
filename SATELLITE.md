# EUMETSAT MTG/FCI satellite nowcast (12.4.0)

The satellite layer is deliberately separate from the long-range model decision. It describes **observed cloud reality now** and a short extrapolative nowcast; it does not directly change `SPUSTIT / NEJISTÉ / NESPOUŠTĚT` in 12.4.0.

## Data source

Quantitative cloud detection uses the EUMETSAT MTG/FCI Level-2 Cloud Mask (CLM), GRIB-2 variant (`EO:EUM:DAT:0800`). The product is generated every 10 minutes at 2 km nadir resolution. The GRIB cloud-mask categories are interpreted as:

- 0 — clear water
- 1 — clear land
- 2 — cloud
- 3 — no data

The backend reuses the existing `ecCodes/grib_get` dependency and samples 17 positions: the observatory plus eight compass directions at R/2 and eight at R.

EUMETSAT catalogue discovery is anonymous, but Data Store downloads require a registered EUMETSAT account and temporary access token generated from a consumer key and consumer secret. The backend generates the temporary token automatically; the long-lived key/secret are configured only in Home Assistant App options.

When no credentials are present the integration is fail-open: existing weather/model decisions continue unchanged, quantitative satellite entities are `unavailable`, and the card offers the public EUMETView MTG IR10.5 visualisation instead. The WMS image is intentionally **not** converted into a fake cloud percentage because it is a styled, non-queryable image rather than geophysical pixel data.

## SD-card protection

Astro Weather is expected to run continuously on small Home Assistant hardware, including Raspberry Pi systems booting from an SD card. Large transient weather files therefore must not create unnecessary flash write amplification.

From 12.4.0:

- the downloaded EUMETSAT SIP/ZIP stays only in Python memory;
- the extracted MTG/FCI GRIB2 is written only to `/dev/shm` (container RAM tmpfs), sampled, and immediately deleted;
- satellite and ALADIN large-GRIB processing share one lock so only one large scratch GRIB is present in RAM at a time;
- ALADIN keeps only its **compressed current-run cache** under `/data/cache`; its temporary decompressed `.grb` is created in `/dev/shm` and removed immediately;
- if `/dev/shm` is unavailable or too small, the backend fails that data source open rather than silently falling back to a large temporary write on the SD card;
- the satellite sample cache remains only a small JSON containing at most seven recent sampled frames, not full satellite images.

A real operational CLM test on 2026-09-12 returned a roughly 3.3 MB compressed SIP with a roughly 22.3 MB GRIB2 payload, so this change avoids repeated multi-megabyte transient writes every ten minutes.

## Home Assistant App options

```yaml
use_satellite: true
satellite_radius_km: 30
satellite_refresh_minutes: 10
satellite_entity: sensor.astro_satelit_oblacnost
satellite_comparison_entity: sensor.astro_model_satelit_shoda
eumetsat_consumer_key: "YOUR_KEY"
eumetsat_consumer_secret: "YOUR_SECRET"
```

The secret is declared as a Home Assistant `password` option and is never published in sensor attributes or logs.

## Published entities

- `sensor.astro_satelit_oblacnost` — observed local neighbourhood cloud fraction from the latest CLM frame. Attributes contain acquisition time, age, trend, 0–3 h nowcast, stable edge/ETA, and the exact 17 CLM sample values shown by the card.
- `sensor.astro_model_satelit_shoda` — current agreement percentage between the complete available MET + ALADIN + ICON cloud consensus and satellite reality.
- `sensor.astro_met_satelit_chyba` — MET absolute error in percentage points against the same satellite observation.
- `sensor.astro_aladin_satelit_chyba` — ALADIN absolute error.
- `sensor.astro_icon_satelit_chyba` — ICON absolute error.

The three error sensors are intended for Home Assistant Recorder/statistics so model performance can be evaluated over many nights instead of judged from individual examples.

## Direction and ETA

Direction is intentionally conservative. It is shown only when **three consecutive satellite frames** contain the same type of clear/cloud edge with compatible bearings. ETA is added only when that consistent edge is also measurably approaching the observatory. This mirrors the strict consistency principle used by the 12.3.4 model-edge logic.

## Short nowcast

The separate card displays `TEĎ`, `+1 h`, `+2 h`, `+3 h`. `TEĎ` is the latest observation; future values are an explicitly labelled short extrapolative nowcast derived from several recent CLM frames. They are not presented as future satellite measurements.

## CLM map on the card

Satellite card v2 displays a lightweight local CLM map by default. It does **not** decode or retain another large image. The map renders the exact 17 categorical samples already used by the backend:

- centre = observatory;
- inner ring = eight directions at R/2;
- outer ring = eight directions at R;
- green = clear;
- light cloud marker = cloud;
- grey = no data.

This makes the visualisation directly auditable while adding virtually no CPU, RAM, or SD-card load. It is deliberately labelled as a sample map rather than an interpolated full-resolution image.

## Dashboard card

After the App has installed/reloaded the Astro card resources, add:

```yaml
type: custom:astro-satellite-card
satellite_entity: sensor.astro_satelit_oblacnost
comparison_entity: sensor.astro_model_satelit_shoda
show_clm_map: true
show_image: false
```

`show_clm_map: true` is the default and shows the exact CLM samples used by the calculation. Set `show_image: true` only when the public EUMETView IR panel is also desired inside the card.

The main `astro-start-card` remains compact: it only shows the current model-consensus versus satellite agreement. Detailed satellite diagnostics stay on the dedicated card and in entity attributes.
