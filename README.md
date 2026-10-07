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

Phase 0 (scope) and Phase 1 (data pipeline) done. Phase 2 (installable app shell) built; see **App** below.

## Data pipeline

| Piece | Where |
|---|---|
| Spot database (25 CA spots, buoy + tide registries) | `spots.json` |
| Fetchers, staleness check, live verifier | `pipeline/` |
| Tests (offline, canned API responses) | `tests/` |
| Workflows | `.github/workflows/` |

Published data lives on the **`data` branch** (one commit, replaced every run), not on `main`. Committing forecasts to `main` every 3 hours would grow the repo by megabytes a day and leave your local copy permanently behind.

```
data branch
  index.json             spots, which buoy is live for each, 72 h outlook per spot
  meta.json              last success / error per source, attribution
  forecast/<spot>.json   hourly waves, swell trains, wind, sun (16 days)
  tides/<station>.json   highs/lows + hourly heights (ft, MLLW)
  buoys/<id>.json        latest reading + last 48 h
  spots.json             copy of the spot database
```

### Workflows

- **CI**: ruff + pytest on every push.
- **Fetch data**: every 3 h; publishes to `data`. Alerts via ntfy if it fails.
- **Staleness check**: every 6 h; alerts via ntfy if any source hasn't updated.
- **Deploy app**: after every successful fetch and on app changes; publishes `app/` plus the `data` branch to GitHub Pages.
- **Send test alert**: manual button that sends one ntfy message; goes red if the secret is missing or ntfy refuses it.
- **Verify sources**: live check of every station ID and API; runs when spots or pipeline code change, and weekly.

### One-time setup (GitHub website)

1. Merge this branch into `main` (scheduled workflows only run from the default branch).
2. Settings → Secrets and variables → Actions → New repository secret:
   - `NTFY_TOPIC`: your long random topic (subscribe to the same topic in the ntfy app).
   - `HEALTHCHECK_URL` (optional, recommended): a ping URL from healthchecks.io. Its free tier alerts you if pings stop, which catches the one failure the staleness check can't: GitHub's scheduler itself stopping. It can notify through ntfy.
3. Actions tab → Fetch data → Run workflow, to publish the first data.

## App

Plain HTML/CSS/JS in `app/`, no build step. GitHub Pages serves it at
`https://padraik99.github.io/wave-finder/` with the data at `./data/` on the same site.

- **Region list**: every spot with the current wave height, wind label and a 72 h bar strip, all from `index.json` (about 5 KB compressed).
- **Spot detail**: hour scrubber (drag the strip, tap a day to jump to first light, or step ±1 h / ±3 h). For the chosen hour: swell trains with an in-window/blocked flag, wind as an arrow against the beach, tide height and direction, water and air temperature, first light / sunrise / sunset / last light. Live buoy panel compares the latest reading with the forecast for that hour.
- **Offline**: a service worker caches the app and every data file you open. Data is network-first with an 8 s timeout, then the saved copy, with an "Offline" banner. The last 3 spots you opened are refreshed in the background while the connection is good.
- **Per refresh**: the region list costs about 5 KB; opening a spot costs about 25 to 35 KB (forecast, tide, buoy). Unchanged files come back as 304s.
- First and last light are computed on the phone (`app/js/sun.js`); its sunrise/sunset agree with Open-Meteo's to within 2 minutes.

### One-time setup for the app

Settings → Pages → Build and deployment → Source: **GitHub Actions**. Then Actions → Deploy app → Run workflow (or wait for the next fetch). On the Pixel, open the URL in Chrome → menu → **Add to home screen / Install**.

### Running locally

```
python tools/serve.py --data path\to\data    # app on http://localhost:8000
npm test                                        # app unit tests (Node 22)
```

### Running the pipeline locally

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pytest
.venv\Scripts\python -m pipeline.verify       # live check, needs internet
.venv\Scripts\python -m pipeline.run --out data
```

## Data credits

Forecast data from [Open-Meteo](https://open-meteo.com/) (ECMWF, NOAA, DWD, Météo-France models). Tides from NOAA CO-OPS. Buoy data from NOAA NDBC and Scripps CDIP. Personal, non-commercial use.
