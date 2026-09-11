## 12.2.0 - 2026-09-11
- Add DWD ICON as a third independent cloud-model family through the Open-Meteo DWD ICON seamless dataset.
- Add a robust multi-model cloud consensus: median plus 20% of the model spread, with explicit confidence, outlier detection and genuine-conflict handling instead of fixed invented weights or simple majority voting.
- Preserve the complete 12.1.12 MET + ALADIN cloud formula whenever ICON is unavailable, so the new source is fail-open.
- Require at least two independent cloud models for a normal good imaging block; a lone model is intentionally low-confidence.
- Validate CHMU ALADIN applicability from the actual nearest native GRIB grid point so installations outside the ALADIN domain do not consume a distant boundary value.
- Add per-hour ICON/model-count/spread/agreement/outlier metadata and per-night two-model/three-model coverage plus ICON averages.
- Add Astro Start Decision Card v23, displaying ICON and multi-model coverage while retaining the known-good v22 card as its internal base module.
- Add permanent GitHub Actions regression CI for the original 12.1 behavior, new ICON/consensus tests, JavaScript syntax and the Home Assistant container build.

## 12.1.12 - 2026-09-11
- Soften the dew-point-margin penalty: heated optics can tolerate dew risk, so low ΔT is now a warning about atmospheric haze/fog rather than an automatic near-stop.
- Keep MET `fog_area_fraction` as the separate strong fog penalty/veto.
- Publish per-hour `scorePenalties` plus `dominantPenalty` and show the largest point loss directly on each hourly tile.
- Increase the default latest acceptable start of a four-hour good block from 90 to 120 minutes after astronomical darkness begins.
- Bump the main decision card to `astro-start-card-v22.js`.

## 12.1.11 - 2026-09-10
- Replace traffic-light hour backgrounds with a blue-to-gray cloud-cover palette; the number remains the total imaging suitability score.
- Read score thresholds from backend settings so the card legend matches `good_score` and `marginal_score`.
- Explain `NEJISTÉ` verdicts caused by a strong MET/ALADIN disagreement with the affected duration and the largest conflicting hourly values.
- Bump the main decision card to `astro-start-card-v21.js`.
- Add a stable `/local/astro-weather-cards-loader.js` resource and no-cache manifest so future physical card versions load without editing Lovelace URLs.
- Create or migrate the loader resource through Home Assistant's authenticated WebSocket API in Lovelace storage mode, consolidating only Astro Weather resource entries.
- Convert existing v20/v22 files to compatibility loaders during upgrade as a fallback for the currently deployed resource paths.

## 12.1.10 - 2026-09-10
- Fix the Moon forecast card name in Home Assistant's card picker; it now reports its real version instead of the stale v19 label.
- Add a default Moon/weather/decision entity configuration so the Moon forecast card works when selected directly from the card picker.
- Bump the physical Moon card file to `moon-forecast-card-v23.js` so Home Assistant cannot reuse the broken cached card.

## 12.1.9 - 2026-09-10
- Install only the physical versioned card files `astro-start-card-v20.js` and `moon-forecast-card-v22.js`.
- Remove the unsupported Lovelace resource REST registration attempt; dashboard resources are a documented one-time manual setting.
- Restore the three published Home Assistant states automatically within one minute after Home Assistant Core restarts.
- Rewrite the installation sequence to include the required first Home Assistant restart and exact verification steps.
- Remove obsolete `?v=` cache-suffix advice and legacy standalone-file migration details from the current installation guide.

## 12.1.8 - 2026-09-09
- Lovelace dashboard resources now use physical versioned files: `/local/astro-start-card-v20.js` and `/local/moon-forecast-card-v22.js`.
- The add-on writes both compatibility card names and versioned card names into `/config/www` on startup.
- This avoids Home Assistant or browser issues with query-string cache suffixes such as `?v=20`.

## 12.1.7 - 2026-09-09
- Lovelace resource auto-install now updates existing astro card resource URLs instead of adding duplicates.
- Dashboard resource cache URLs are now astro-start-card v20 and moon-forecast-card v22.
- This avoids an old cached card registering the custom element before the new module loads.

## 12.1.6 - 2026-09-09
- Dashboard cards are force-copied to /config/www on every add-on start, even when old files already exist.
- Startup log now includes the first line of each copied card, making the active card version visible in the add-on log.
- The add-on now tries to register Lovelace resources automatically through the Home Assistant API.
- Dashboard resource cache URLs are now astro-start-card v19 and moon-forecast-card v21.

## 12.1.5 - 2026-09-09
- Bumped dashboard-card cache versions to astro-start-card v18 and moon-forecast-card v20.
- Dashboard card source links display CAMS/Open-Meteo and 7Timer only.
- Documentation now uses Lovelace resources with `?v=18` and `?v=20`.

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
