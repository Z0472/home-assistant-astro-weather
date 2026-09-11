from pathlib import Path


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


backend = Path("astro_weather_backend/astro_weather_backend.py")
text = backend.read_text(encoding="utf-8")
text = once(
    text,
    '    score = max(0.0, min(100.0, 100.0 - sum(score_penalties.values())))\n',
    '    score = (\n        0.0\n        if effective_cloud is None\n        else max(0.0, min(100.0, 100.0 - sum(score_penalties.values())))\n    )\n',
    "missing-cloud score preservation",
)
text = once(
    text,
    '''    if precip is not None and precip > 0:\n        dominant_penalty = {"key": "precip", "label": "srážky", "points": 100.0}\n    elif moon_interferes:\n        dominant_penalty = {"key": "moon", "label": "Měsíc", "points": 100.0}\n    else:\n        dominant_key, dominant_points = max(score_penalties.items(), key=lambda item: item[1])\n''',
    '''    if precip is not None and precip > 0:\n        dominant_penalty = {"key": "precip", "label": "srážky", "points": 100.0}\n    elif moon_interferes:\n        dominant_penalty = {"key": "moon", "label": "Měsíc", "points": 100.0}\n    elif effective_cloud is None:\n        dominant_penalty = None\n    else:\n        dominant_key, dominant_points = max(score_penalties.items(), key=lambda item: item[1])\n''',
    "missing-cloud dominant factor",
)
backend.write_text(text, encoding="utf-8")

tests = Path("tests/test_astro_weather_backend.py")
t = tests.read_text(encoding="utf-8")
marker = '\n\nif __name__ == "__main__":\n'
method = '''
    def test_missing_all_cloud_models_keeps_zero_score(self):
        row = self.forecast(0.1)[0]
        row["met"] = None
        row["aladin"] = None
        scored = b.score_hour(row, None, self.night, self.options)
        self.assertEqual(scored["score"], 0)
        self.assertEqual(scored["status"], "bad")
        self.assertIsNone(scored["dominantPenalty"])

'''
if method.strip() not in t:
    if marker not in t:
        raise SystemExit("test insertion marker missing")
    t = t.replace(marker, "\n" + method + marker, 1)
tests.write_text(t, encoding="utf-8")
