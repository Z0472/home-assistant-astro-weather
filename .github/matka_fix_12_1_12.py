from pathlib import Path

# The main patch creates v22; finish the version-specific card/test references
# that are intentionally separate from the runtime version constants.
for filename in (
    "astro_weather_backend/cards/astro-start-card.js",
    "cards/astro-start-card-v22.txt",
):
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    text = text.replace('name: "Astro Start Decision Card v21"', 'name: "Astro Start Decision Card v22"')
    path.write_text(text, encoding="utf-8")

path = Path("tests/test_astro_weather_backend.py")
text = path.read_text(encoding="utf-8")
text = text.replace("cards/astro-start-card-v21.txt", "cards/astro-start-card-v22.txt")
text = text.replace('self.assertIn("astro-start-card v21", bundled)', 'self.assertIn("astro-start-card v22", bundled)')
text = text.replace('self.assertIn(\'name: "Astro Start Decision Card v21"\', bundled)', 'self.assertIn(\'name: "Astro Start Decision Card v22"\', bundled)')
path.write_text(text, encoding="utf-8")
