# Wave Finder

A personal, ad-free surf and wave-watching app for the California coast, built as an installable web app (PWA) for a Pixel phone.

It answers three questions:

1. **Where should we go, and when?** Pick a stretch of coast, tap a spot, scrub to the hour you'll be there.
2. **Is Mavericks going off?** Push alerts days ahead, then a confirmation when the swell arrives.
3. **Where is this swell coming from?** Follow a North Pacific storm from birth to arrival at Pillar Point.

## How it works

- A Python script runs every few hours on GitHub Actions. It pulls free public data (Open-Meteo marine and wind forecasts, NOAA tides, NDBC/CDIP buoys) and publishes JSON.
- The app is plain HTML/CSS/JavaScript served from GitHub Pages. It reads that JSON and caches it, so the last forecast still works with weak signal on the coast.
- Alerts go to the ntfy app on Android.

## Status

Phase 0 (scope) is done. Phase 1 (data pipeline) is next.

## Data credits

Forecast data from [Open-Meteo](https://open-meteo.com/) (ECMWF, NOAA, DWD, Météo-France models). Tides from NOAA CO-OPS. Buoy data from NOAA NDBC and Scripps CDIP. Personal, non-commercial use.
