# Changelog

## 12.1.4 - 2026-09-09

- Replace bundled latitude, longitude and altitude with public-safe sample defaults.
- Keep real observing location only in each Home Assistant app configuration.
- Keep the generic repository-based MET User-Agent.
- No decision algorithm changes from 12.1.3.

## 12.1.3 - 2026-09-09

- Replace the default MET User-Agent with a generic repository-based value.
- Remove the personal domain and observatory hint from public default configuration.
- No decision algorithm changes from 12.1.2.

## 12.1.2 - 2026-09-09

- Clarify that the supported install path is through the Home Assistant App/Add-on Store repository flow, not copying files into `/addons`.
- Add the repository URL to add-on metadata.
- Bump runtime metadata so Home Assistant can see a fresh update.
- No decision algorithm changes from 12.1.1.

## 12.1.1 - 2026-09-09

- Remove remaining old source link from dashboard card source headers.
- Point card source links directly to CAMS/Open-Meteo and 7Timer.
- Bump bundled dashboard cards to `astro-start-card v17` and `moon-forecast-card v19` for browser cache refresh.
- No decision algorithm changes from 12.1.0.

## 12.1.0 - 2026-09-09

- Add automatic dashboard card installation from the add-on image into `/config/www`.
- Add `homeassistant_config` mapping at `/ha_config` and new `install_dashboard_cards` option.
- Include stable `astro-start-card.js` and `moon-forecast-card.js` inside the add-on build context.
- Document GitHub repository install/update flow instead of manual file copying.

## 12.0.1 - 2026-09-09

- Metadata/cache-buster release for Home Assistant Supervisor local app installs that kept showing the previous installed version.
- No decision algorithm changes from 12.0.0.

## 12.0.0 - 2026-09-09

- Removed SkyAccuracy.cz dependency from the backend.
- Fetch CAMS AOD 550 directly through the Open-Meteo Air Quality API.
- Fetch seeing directly from the 7Timer ASTRO JSON API and expand sparse forecast steps to hourly values.
- Keep AOD and seeing fail-open: stale or unavailable sources are ignored and MET + ALADIN + internal Moon continue to drive the decision.
- Store Open-Meteo dust as `dust_ugm3` / `dustUgm3`, because it is surface concentration, not dust AOD.
- Updated dashboard cards to v16/v18 with direct CAMS/Open-Meteo and 7Timer source labels.

## 11.0.0 - 2026-09-09

- Added internal Moon and astronomical-night calculation directly in the backend.
- Removed runtime dependency on Home Assistant Moon command_line/package sensors.
- Backend now publishes Home Assistant entities through the Supervisor API:
  - sensor.astro_weather_detail
  - sensor.astro_vhodnost_foceni
  - sensor.mesic_foceni_predpoved
- Kept SkyAccuracy AOD 550, dust and 7Timer seeing as optional guarded inputs.
- Added tests for internal Moon generation and Home Assistant entity publishing.
