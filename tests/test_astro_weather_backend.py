"""Offline checks for Astro Weather Backend."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "astro_weather_backend"))
import astro_weather_backend as b


class AerosolTests(unittest.TestCase):
    def setUp(self):
        with patch.object(b, "OPTIONS_FILE", Path("/nonexistent/astro_test_options.json")):
            self.options = b.load_options()
        self.start = datetime(2026, 9, 8, 19, tzinfo=timezone.utc)
        self.night = {"date": "2026-09-08", "status": "nerusi",
                      "astronomical_dark_start": b.iso_z(self.start),
                      "astronomical_dark_end": b.iso_z(self.start + timedelta(hours=8))}

    def forecast(self, aod=0.1):
        return [{"datetime": b.iso_z(self.start + timedelta(hours=i)),
                 "met": {"cloud_total": 0, "cloud_high": 0, "temperature": 15,
                         "dew_point": 5, "fog": 0, "precipitation_1h": 0, "wind_speed_ms": 2},
                 "aladin": {"cloud_total": 0, "cloud_high": 0},
                 "aerosols": {"aod550": aod, "dust_ugm3": 2.0, "stale": False},
                 "seeing": None}
                for i in range(8)]

    def analyze(self, rows):
        return b.analyze_night(self.night, rows, [], self.options)

    def open_meteo_document(self, times, aod, dust=None):
        return {"latitude": self.options["latitude"], "longitude": self.options["longitude"],
                "hourly": {"time": times, "aerosol_optical_depth": aod, "dust": dust or [None] * len(times)}}

    def seven_timer_document(self, rows, init="2026090816"):
        return {"product": "astro", "init": init, "dataseries": rows}

    def test_internal_moon_document_has_future_night(self):
        now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
        self.options["moon_horizon_days"] = 3
        with patch.object(b, "utc_now", return_value=now):
            doc = b.build_internal_moon_document(self.options)
        attrs = doc["attributes"]
        self.assertEqual(attrs["provider"], "Astro Weather Backend internal Moon")
        self.assertGreaterEqual(len(attrs["daily"]), 5)
        self.assertTrue(any(night.get("astronomical_dark_start") for night in attrs["daily"]))
        self.assertTrue(attrs["hourly"])
        self.assertIn("moon_illumination", attrs["hourly"][0])
        self.assertNotEqual(doc["state"], "BEZ DAT")

    def test_publishes_home_assistant_entities(self):
        weather = {"state": "ok", "forecast": [], "backend_version": b.APP_VERSION}
        decision = {"state": "SPUSTIT", "machine_state": "good", "daily": []}
        moon = {"state": "7.2 h", "attributes": {"daily": [], "hourly": []}}
        with patch.object(b, "publish_home_assistant_state") as publish:
            b.publish_homeassistant_entities(self.options, weather, decision, moon)
        self.assertEqual(
            [call.args[0] for call in publish.call_args_list],
            [
                "sensor.astro_weather_detail",
                "sensor.astro_vhodnost_foceni",
                "sensor.mesic_foceni_predpoved",
            ],
        )
        self.assertEqual(publish.call_args_list[2].args[2]["friendly_name"], "Měsíc focení předpověď")

    def test_dashboard_install_writes_versioned_cards_and_stable_loader(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as config_dir:
            source = Path(source_dir)
            source.joinpath("astro-start-card.js").write_text("astro v22", encoding="utf-8")
            source.joinpath("moon-forecast-card.js").write_text("moon v23", encoding="utf-8")
            source.joinpath("astro-weather-cards-loader.js").write_text("loader", encoding="utf-8")
            with patch.object(b, "DASHBOARD_CARDS_DIR", source), \
                    patch.object(b, "HA_CONFIG_DIR", Path(config_dir)), \
                    patch.object(b, "log"):
                install_ok = b.install_dashboard_cards(self.options)

            installed = Path(config_dir) / "www"
            self.assertTrue(install_ok)
            self.assertEqual(
                sorted(path.name for path in installed.iterdir()),
                [
                    "astro-start-card-v22.js",
                    "astro-weather-cards-loader.js",
                    "astro-weather-cards-manifest.json",
                    "moon-forecast-card-v23.js",
                ],
            )
            manifest = json.loads(installed.joinpath("astro-weather-cards-manifest.json").read_text())
            self.assertEqual(manifest["backend_version"], b.APP_VERSION)
            self.assertEqual(
                [card["url"] for card in manifest["cards"]],
                ["/local/astro-start-card-v22.js", "/local/moon-forecast-card-v23.js"],
            )

    def test_dashboard_install_converts_existing_resource_files_to_loader(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as config_dir:
            source = Path(source_dir)
            source.joinpath("astro-start-card.js").write_text("astro v22", encoding="utf-8")
            source.joinpath("moon-forecast-card.js").write_text("moon v23", encoding="utf-8")
            source.joinpath("astro-weather-cards-loader.js").write_text("loader", encoding="utf-8")
            installed = Path(config_dir) / "www"
            installed.mkdir()
            installed.joinpath("astro-start-card-v20.js").write_text("old astro", encoding="utf-8")
            installed.joinpath("moon-forecast-card-v22.js").write_text("old moon", encoding="utf-8")

            with patch.object(b, "DASHBOARD_CARDS_DIR", source), \
                    patch.object(b, "HA_CONFIG_DIR", Path(config_dir)), \
                    patch.object(b, "log"):
                install_ok = b.install_dashboard_cards(self.options)

            self.assertTrue(install_ok)
            for filename in ("astro-start-card-v20.js", "moon-forecast-card-v22.js"):
                compatibility = installed.joinpath(filename).read_text(encoding="utf-8")
                self.assertIn('/local/astro-weather-cards-loader.js', compatibility)

    def test_lovelace_resources_are_consolidated_to_stable_loader(self):
        class FakeSocket:
            def __init__(self):
                self.responses = []
                self.commands = []

            def send(self, raw):
                command = json.loads(raw)
                self.commands.append(command)
                result = None
                if command["type"] == "lovelace/resources/update":
                    result = {
                        "id": command["resource_id"],
                        "url": command["url"],
                        "type": command["res_type"],
                    }
                self.responses.append(json.dumps({
                    "id": command["id"],
                    "type": "result",
                    "success": True,
                    "result": result,
                }))

            def recv(self):
                return self.responses.pop(0)

        socket = FakeSocket()
        actions = b._sync_lovelace_loader_resource(socket, [
            {"id": "astro", "url": "/local/astro-start-card-v20.js", "type": "module"},
            {"id": "moon", "url": "/local/moon-forecast-card-v22.js", "type": "module"},
            {"id": "other", "url": "/local/other-card.js", "type": "module"},
        ], allow_create=True)

        self.assertEqual(
            [command["type"] for command in socket.commands],
            ["lovelace/resources/update", "lovelace/resources/delete"],
        )
        self.assertEqual(socket.commands[0]["resource_id"], "astro")
        self.assertEqual(socket.commands[0]["url"], "/local/astro-weather-cards-loader.js")
        self.assertEqual(socket.commands[1]["resource_id"], "moon")
        self.assertTrue(any("astro-start-card-v20.js" in action for action in actions))

    def test_lovelace_loader_resource_is_created_on_clean_install(self):
        class FakeSocket:
            def __init__(self):
                self.response = None

            def send(self, raw):
                command = json.loads(raw)
                self.command = command
                self.response = json.dumps({
                    "id": command["id"],
                    "type": "result",
                    "success": True,
                    "result": {
                        "id": "created",
                        "url": command["url"],
                        "type": command["res_type"],
                    },
                })

            def recv(self):
                return self.response

        socket = FakeSocket()
        actions = b._sync_lovelace_loader_resource(socket, [], allow_create=True)
        self.assertEqual(socket.command["type"], "lovelace/resources/create")
        self.assertEqual(socket.command["url"], "/local/astro-weather-cards-loader.js")
        self.assertEqual(actions, ["pridano /local/astro-weather-cards-loader.js"])

    def test_lovelace_websocket_authenticates_and_migrates_resource(self):
        class FakeSocket:
            def __init__(self):
                self.responses = [json.dumps({"type": "auth_required"})]
                self.commands = []
                self.closed = False

            def send(self, raw):
                command = json.loads(raw)
                self.commands.append(command)
                if command["type"] == "auth":
                    self.responses.append(json.dumps({"type": "auth_ok"}))
                    return
                if command["type"] == "lovelace/resources/list":
                    result = [{
                        "id": "astro",
                        "url": "/local/astro-start-card-v20.js",
                        "type": "module",
                    }]
                elif command["type"] == "lovelace/resources/update":
                    result = {
                        "id": command["resource_id"],
                        "url": command["url"],
                        "type": command["res_type"],
                    }
                else:
                    result = None
                self.responses.append(json.dumps({
                    "id": command["id"],
                    "type": "result",
                    "success": True,
                    "result": result,
                }))

            def recv(self):
                return self.responses.pop(0)

            def close(self):
                self.closed = True

        socket = FakeSocket()

        class FakeWebsocketClient:
            @staticmethod
            def create_connection(*args, **kwargs):
                return socket

        with patch.dict(sys.modules, {"websocket": FakeWebsocketClient}), \
                patch.dict(b.os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            actions = b.ensure_lovelace_loader_resource(self.options)

        self.assertEqual(socket.commands[0], {"type": "auth", "access_token": "test-token"})
        self.assertEqual(socket.commands[1]["type"], "lovelace/resources/list")
        self.assertEqual(socket.commands[2]["type"], "lovelace/resources/update")
        self.assertTrue(socket.closed)
        self.assertTrue(any("astro-weather-cards-loader.js" in action for action in actions))

    def test_moon_card_picker_has_current_version_and_working_defaults(self):
        repository_root = Path(__file__).resolve().parents[1]
        bundled = repository_root.joinpath(
            "astro_weather_backend/cards/moon-forecast-card.js"
        ).read_text(encoding="utf-8")
        downloadable = repository_root.joinpath(
            "cards/moon-forecast-card-v23.txt"
        ).read_text(encoding="utf-8")

        self.assertEqual(bundled, downloadable)
        self.assertIn("Moon Forecast Card v23", bundled)
        self.assertIn('name: "Moon Forecast Card v23"', bundled)
        self.assertIn("static getStubConfig()", bundled)
        self.assertIn('entity: "sensor.mesic_foceni_predpoved"', bundled)
        self.assertIn('weather_entity: "sensor.astro_weather_detail"', bundled)
        self.assertIn('decision_entity: "sensor.astro_vhodnost_foceni"', bundled)

    def test_astro_card_has_current_version_loader_and_cloud_palette(self):
        repository_root = Path(__file__).resolve().parents[1]
        bundled = repository_root.joinpath(
            "astro_weather_backend/cards/astro-start-card.js"
        ).read_text(encoding="utf-8")
        downloadable = repository_root.joinpath(
            "cards/astro-start-card-v22.txt"
        ).read_text(encoding="utf-8")
        loader = repository_root.joinpath(
            "astro_weather_backend/cards/astro-weather-cards-loader.js"
        ).read_text(encoding="utf-8")

        self.assertEqual(bundled, downloadable)
        self.assertIn("astro-start-card v22", bundled)
        self.assertIn('name: "Astro Start Decision Card v22"', bundled)
        self.assertIn("#1565c0", bundled)
        self.assertIn("#a7aaad", bundled)
        self.assertNotIn("80–100 výborné", bundled)
        self.assertIn("astro-weather-cards-manifest.json", loader)
        self.assertIn('cache: "no-store"', loader)

    def test_missing_entities_are_republished_from_cached_state(self):
        weather = {"state": "ok", "generated_at": "2026-09-10T08:00:00Z", "forecast": []}
        decision = {"state": "SPUSTIT", "machine_state": "good", "daily": []}
        moon = {"state": "7.2 h", "attributes": {"daily": [], "hourly": []}}
        with patch.object(b, "STATE", weather), \
                patch.object(b, "DECISION_STATE", decision), \
                patch.object(b, "MOON_STATE", moon), \
                patch.object(b, "home_assistant_state_exists", side_effect=lambda entity_id: entity_id == "sensor.astro_weather_detail"), \
                patch.object(b, "publish_homeassistant_entities") as publish, \
                patch.object(b, "log"):
            changed = b.republish_missing_homeassistant_entities(self.options)

        self.assertTrue(changed)
        publish.assert_called_once()

    def test_entity_watchdog_does_nothing_when_all_entities_exist(self):
        with patch.object(b, "home_assistant_state_exists", return_value=True), \
                patch.object(b, "publish_homeassistant_entities") as publish:
            changed = b.republish_missing_homeassistant_entities(self.options)

        self.assertFalse(changed)
        publish.assert_not_called()

    def test_thresholds(self):
        for aod, expected in [(0, "good"), (0.1, "good"), (0.2, "good"),
                              (0.299, "good"), (0.3, "uncertain"), (0.399, "uncertain"), (0.4, "bad")]:
            with self.subTest(aod=aod):
                self.assertEqual(self.analyze(self.forecast(aod))["decision"], expected)

    def test_pollution_breaks_early_continuous_block(self):
        rows = self.forecast()
        rows[2]["aerosols"]["aod550"] = 0.45
        a = self.analyze(rows)
        self.assertEqual(a["launchBlock"]["hours"], 2)
        self.assertEqual(a["bestBlock"]["hours"], 5)
        self.assertEqual(a["decision"], "bad")
        self.assertIn("zákal", a["reason"])

    def test_missing_falls_back_without_inventing_zero(self):
        a = self.analyze(self.forecast(None))
        self.assertEqual(a["decision"], "good")
        self.assertIsNone(a["aodAvg"])
        self.assertEqual(a["aerosolCoverage"], 0)
        self.assertEqual(a["launchBlock"]["hours"], 8)
        self.assertEqual(a["aerosolMode"], "fallback")
        self.assertEqual(a["aerosolFallbackHours"], 8)
        self.assertIn("průzračnost neověřena", a["reason"])

    def test_stale_high_aod_does_not_penalize_or_block(self):
        rows = self.forecast(.9)
        for row in rows:
            row["aerosols"]["stale"] = True
        a = self.analyze(rows)
        self.assertEqual(a["decision"], "good")
        self.assertEqual(a["aerosolCoverage"], 0)
        self.assertIsNone(a["aodMax"])
        self.assertIsNone(a["dustAodAvg"])
        self.assertIsNone(a["dustUgm3Avg"])
        self.assertIsNone(a["launchBlock"]["aodAvg"])
        self.assertEqual(a["hours"][0]["score"], 100)
        self.assertEqual(a["hours"][0]["confidence"], 100)
        self.assertEqual(a["hours"][0]["aod550"], .9)
        self.assertEqual(a["hours"][0]["aerosolStatus"], "stale")
        self.assertNotIn("Silný zákal", a["reason"])

    def test_partial_outage_keeps_valid_aerosols(self):
        rows = self.forecast(.2)
        rows[0]["aerosols"] = None
        rows[1]["aerosols"] = {"aod550": .8, "stale": True}
        a = self.analyze(rows)
        self.assertEqual(a["aerosolMode"], "partial")
        self.assertEqual(a["aerosolFallbackHours"], 2)
        self.assertEqual(a["aerosolCoverage"], .75)
        self.assertEqual(a["aodAvg"], .2)
        self.assertEqual(a["aodMax"], .2)
        self.assertEqual(a["hours"][0]["score"], 100)
        self.assertLess(a["hours"][2]["score"], 100)
        rows[2]["aerosols"]["aod550"] = .45
        self.assertEqual(self.analyze(rows)["decision"], "bad")

    def test_recovery_automatically_reenables_aerosols(self):
        self.assertEqual(self.analyze(self.forecast(None))["decision"], "good")
        recovered = self.analyze(self.forecast(.45))
        self.assertEqual(recovered["decision"], "bad")
        self.assertEqual(recovered["aerosolMode"], "full")
        self.assertIsNone(recovered["aerosolWarning"])
        self.assertTrue(self.options["use_aerosols"])

    def test_bad_weather_stays_bad_when_aod_missing(self):
        rows = self.forecast(None)
        for row in rows:
            row["met"]["cloud_total"] = 100
            row["aladin"]["cloud_total"] = 100
        self.assertEqual(self.analyze(rows)["decision"], "bad")

    def test_dust_not_penalized_twice(self):
        left, right = self.forecast(0.2), self.forecast(0.2)
        for row in right:
            row["aerosols"]["dust_ugm3"] = 150
        self.assertEqual(self.analyze(left)["hours"][0]["score"], self.analyze(right)["hours"][0]["score"])
        self.assertEqual(self.analyze(right)["dustUgm3Avg"], 150)

    def test_partial_night_average_is_time_weighted(self):
        self.night["astronomical_dark_start"] = b.iso_z(self.start + timedelta(minutes=30))
        rows = self.forecast(0.1)
        rows[0]["aerosols"]["aod550"] = 0.2
        self.assertAlmostEqual(self.analyze(rows)["aodAvg"], (0.5 * 0.2 + 7 * 0.1) / 7.5, places=3)

    def test_open_meteo_values_zero_null_negative_and_wrong_location(self):
        doc = self.open_meteo_document(
            ["2026-09-08T19:00", "2026-09-08T20:00", "2026-09-08T21:00"],
            [0, None, -1],
            [0, 5.5, 2.0],
        )
        parsed = b.parse_open_meteo_air_quality(doc, self.options)
        self.assertEqual(list(parsed), [b.iso_z(self.start)])
        row = parsed[b.iso_z(self.start)]
        self.assertEqual(row["aod550"], 0)
        self.assertIsNone(row["dust_aod550"])
        self.assertEqual(row["dust_ugm3"], 0)
        doc["latitude"] = self.options["latitude"] + 2
        with self.assertRaises(ValueError):
            b.parse_open_meteo_air_quality(doc, self.options)

    def test_cache_fresh_stale_and_expired(self):
        now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
        self.options["horizon_hours"] = 24
        with tempfile.TemporaryDirectory() as directory, patch.object(b, "CACHE_DIR", Path(directory)), patch.object(b, "utc_now", return_value=now):
            for age_hours, expect_available, expect_stale in [(1, True, False), (4, True, True), (7, False, False)]:
                doc = self.open_meteo_document(["2026-09-08T19:00"], [.1], [1.2])
                path = Path(directory) / f"open_meteo_cams_aod_{self.options['latitude']:.4f}_{self.options['longitude']:.4f}.json"
                path.write_text(json.dumps({"fetched_at": b.iso_z(now - timedelta(hours=age_hours)), "payload": doc}))
                with patch.object(b.urllib.request, "urlopen", side_effect=OSError("test outage")) as fetch:
                    rows, source = b.fetch_aerosols(self.options)
                    self.assertEqual(bool(rows), expect_available)
                    self.assertEqual(bool(source["stale_hours"]), expect_stale)
                    self.assertEqual(fetch.call_count, 0 if age_hours == 1 else 1)

    def test_open_meteo_uncached_makes_single_request(self):
        now = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
        self.options["horizon_hours"] = 24
        with tempfile.TemporaryDirectory() as directory, patch.object(b, "CACHE_DIR", Path(directory)), patch.object(b, "utc_now", return_value=now), patch.object(b.urllib.request, "urlopen", side_effect=OSError("test outage")) as fetch:
            _, source = b.fetch_aerosols(self.options)
            self.assertEqual(fetch.call_count, 1)
            self.assertIn("open_meteo", source["errors"])

    def test_configured_thresholds(self):
        self.options.update(aod_warn=.15, aod_bad=.25)
        self.assertEqual(self.analyze(self.forecast(.15))["decision"], "uncertain")
        self.assertEqual(self.analyze(self.forecast(.25))["decision"], "bad")

    def test_uncertain_verdict_explains_strong_model_disagreement(self):
        self.options["use_aerosols"] = False
        self.options["use_seeing"] = False
        rows = self.forecast(None)
        for index, row in enumerate(rows):
            if index < 2:
                row["met"]["cloud_total"] = 100
                row["aladin"]["cloud_total"] = 0
            else:
                row["met"]["cloud_total"] = 100
                row["aladin"]["cloud_total"] = 100

        analysis = self.analyze(rows)
        self.assertEqual(analysis["decision"], "uncertain")
        self.assertEqual(analysis["usableHours"], 0)
        self.assertEqual(analysis["modelDisagreementHours"], 2)
        self.assertTrue(analysis["hours"][0]["strongDisagreement"])
        self.assertIn("Modely MET a ALADIN", analysis["reason"])
        self.assertIn("MET 100 %", analysis["reason"])
        self.assertIn("ALADIN 0 %", analysis["reason"])

    def test_disabled_restores_weather_decision(self):
        self.options["use_aerosols"] = False
        for aod in [None, 0.8]:
            a = self.analyze(self.forecast(aod))
            self.assertEqual(a["decision"], "good")
            self.assertEqual(a["hours"][0]["score"], 100)
            self.assertEqual(a["aerosolMode"], "disabled")
            self.assertIsNone(a["aerosolWarning"])
            self.assertEqual(a["aerosolFallbackHours"], 0)

    def test_fallback_does_not_upgrade_single_weather_model(self):
        rows = self.forecast(None)
        for row in rows:
            row["aladin"] = None
        self.assertEqual(self.analyze(rows)["decision"], "uncertain")

    def test_malformed_api_falls_back(self):
        import io
        now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
        self.options["horizon_hours"] = 24
        with tempfile.TemporaryDirectory() as directory, patch.object(b, "CACHE_DIR", Path(directory)), patch.object(b, "utc_now", return_value=now), patch.object(b.urllib.request, "urlopen", side_effect=lambda *a, **k: io.BytesIO(b'{"changed_schema":true}')):
            data, source = b.fetch_aerosols(self.options)
            self.assertEqual(data, {})
            self.assertTrue(source["errors"])
            rows = self.forecast()
            for row in rows:
                row["aerosols"] = data.get(row["datetime"])
            self.assertEqual(self.analyze(rows)["aerosolMode"], "fallback")
            self.assertEqual(self.analyze(rows)["decision"], "good")

    def test_refresh_survives_aerosol_exception(self):
        from contextlib import ExitStack
        rows = self.forecast(None)
        now = self.start - timedelta(hours=2)
        with ExitStack() as stack:
            stack.enter_context(patch.object(b, "utc_now", return_value=now))
            stack.enter_context(patch.object(b, "fetch_met", return_value=({r["datetime"]: r["met"] for r in rows}, {"available": True})))
            stack.enter_context(patch.object(b, "fetch_aladin", return_value=({r["datetime"]: r["aladin"] for r in rows}, {"available": True})))
            stack.enter_context(patch.object(b, "build_internal_moon_document", return_value={"state": "8.0 h", "last_updated": b.iso_z(now), "attributes": {"daily": [self.night], "hourly": []}}))
            stack.enter_context(patch.object(b, "fetch_sky_quality", side_effect=TimeoutError("test outage")))
            stack.enter_context(patch.object(b, "publish_homeassistant_entities"))
            stack.enter_context(patch.object(b, "STATE", {}))
            stack.enter_context(patch.object(b, "DECISION_STATE", {}))
            stack.enter_context(patch.object(b, "log"))
            b.refresh_once(self.options)
            self.assertEqual(b.STATE["state"], "ok")
            self.assertEqual(b.STATE["errors"]["aerosols"], "test outage")
            self.assertEqual(b.DECISION_STATE["machine_state"], "good")
            self.assertEqual(b.DECISION_STATE["daily"][0]["aerosolMode"], "fallback")

    def test_parse_seeing_values(self):
        self.options["use_aerosols"] = False
        rows = [
            {"timepoint": 3, "seeing": 1, "transparency": 3},
            {"timepoint": 4, "seeing": 8},
        ]
        parsed = b.parse_7timer_astro(self.seven_timer_document(rows), self.options)
        first = parsed[b.iso_z(self.start)]
        second = parsed[b.iso_z(self.start + timedelta(hours=1))]
        self.assertEqual(first["seeingArcsec"], 0.5)
        self.assertEqual(first["seeingDisplay"], "0.5")
        self.assertEqual(first["transparencyIndex"], 3)
        self.assertEqual(second["seeingArcsec"], 3.0)
        self.assertEqual(second["seeingDisplay"], ">2.5")

    def test_7timer_sparse_values_expand_to_hourly_nearest(self):
        rows = [
            {"timepoint": 3, "seeing": 3},
            {"timepoint": 6, "seeing": 5},
        ]
        parsed = b.parse_7timer_astro(self.seven_timer_document(rows), self.options)
        expanded = b.expand_sparse_seeing(parsed)
        self.assertIn(b.iso_z(self.start + timedelta(hours=1)), expanded)
        self.assertEqual(expanded[b.iso_z(self.start + timedelta(hours=1))]["seeingIndex"], 3)
        self.assertEqual(expanded[b.iso_z(self.start + timedelta(hours=2))]["seeingIndex"], 5)

    def test_bad_seeing_can_break_block(self):
        rows = self.forecast()
        for row in rows:
            row["seeing"] = {"seeingArcsec": 1.0, "seeingIndex": 3, "seeingDisplay": "1", "stale": False}
        rows[2]["seeing"] = {"seeingArcsec": 3.0, "seeingIndex": 8, "seeingDisplay": ">2.5", "stale": False}
        a = self.analyze(rows)
        self.assertEqual(a["hours"][2]["status"], "bad")
        self.assertEqual(a["launchBlock"]["hours"], 2)
        self.assertIn("seeing", a["reason"])

    def test_missing_seeing_falls_back_without_penalty(self):
        rows = self.forecast()
        a = self.analyze(rows)
        self.assertEqual(a["decision"], "good")
        self.assertEqual(a["seeingMode"], "fallback")
        self.assertEqual(a["seeingFallbackHours"], 8)
        self.assertIsNone(a["seeingAvg"])
        self.assertEqual(a["hours"][0]["score"], 100)

    def test_disabled_seeing_restores_weather_decision(self):
        self.options["use_seeing"] = False
        rows = self.forecast()
        for row in rows:
            row["seeing"] = {"seeingArcsec": 3.0, "seeingIndex": 8, "seeingDisplay": ">2.5", "stale": False}
        a = self.analyze(rows)
        self.assertEqual(a["decision"], "good")
        self.assertEqual(a["seeingMode"], "disabled")
        self.assertEqual(a["hours"][0]["seeingStatus"], "disabled")

    def test_precipitation_and_moon_remain_vetoes(self):
        rows = self.forecast(None)
        rows[0]["met"]["precipitation_1h"] = .1
        self.assertEqual(self.analyze(rows)["hours"][0]["status"], "bad")
        scored = b.score_hour(rows[1], {"interferes": True}, self.night, self.options)
        self.assertEqual(scored["status"], "bad")
        self.assertEqual(scored["score"], 0)


    def test_dew_penalty_is_soft_and_reports_dominant_factor(self):
        self.assertEqual(b.dew_penalty(3.0), 0.0)
        self.assertAlmostEqual(b.dew_penalty(2.0), 10.0)
        self.assertAlmostEqual(b.dew_penalty(1.0), 20.0)
        self.assertAlmostEqual(b.dew_penalty(0.9), 22.0)
        self.assertAlmostEqual(b.dew_penalty(0.5), 30.0)
        self.assertEqual(b.dew_penalty(0.4), 40.0)

        row = self.forecast(0.1)[0]
        row["met"]["dew_point"] = 14.1
        scored = b.score_hour(row, None, self.night, self.options)
        self.assertAlmostEqual(scored["score"], 78.0)
        self.assertEqual(scored["dominantPenalty"]["key"], "dew")
        self.assertAlmostEqual(scored["dominantPenalty"]["points"], 22.0)

    def test_default_launch_window_accepts_block_starting_two_hours_late(self):
        self.assertEqual(self.options["max_start_delay_minutes"], 120)
        rows = self.forecast(0.1)
        for row in rows[:2]:
            row["met"]["cloud_total"] = 100
            row["aladin"]["cloud_total"] = 100
        analysis = self.analyze(rows)
        self.assertEqual(analysis["decision"], "good")
        self.assertEqual(analysis["launchBlock"]["hours"], 6)



if __name__ == "__main__":
    unittest.main()
