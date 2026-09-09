# Dashboard Cards

The current card sources are kept here as TXT files for easy download and inspection:

- `astro-start-card-v17.txt`
- `moon-forecast-card-v19.txt`

From add-on version 12.1.1 the same cards are also bundled inside the add-on image and copied automatically on startup to:

- `/config/www/astro-start-card.js`
- `/config/www/moon-forecast-card.js`

Use these Lovelace resources in Home Assistant:

```text
/local/astro-start-card.js?v=17
/local/moon-forecast-card.js?v=19
```

The TXT files are still useful as a manual fallback, but the normal install path is now the add-on.
