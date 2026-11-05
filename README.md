# Wave Finder

A personal, ad-free surf and wave-watching app for the California coast, built as an installable web app (PWA) for a Pixel phone.

It answers three questions:

1. **Where should we go, and when?** Pick a stretch of coast, tap a spot, scrub to the hour you'll be there.
2. **Is Mavericks going off?** Push alerts days ahead, then a confirmation when the swell arrives.
3. **Where is this swell coming from?** Follow a North Pacific storm from birth to arrival at Pillar Point.

## How it works

- A Python script runs hourly on GitHub Actions. It pulls free public data (Open-Meteo marine and wind forecasts, NOAA tides, NDBC/CDIP buoys) and publishes JSON.
- The app is plain HTML/CSS/JavaScript served from GitHub Pages. It reads that JSON and caches it, so the last forecast still works with weak signal on the coast.
- Alerts go to the ntfy app on Android.

## Status

Phase 0 (scope) and Phase 1 (data pipeline) done. Phase 2 (installable app shell) built; see **App** below.

## Data pipeline

| Piece | Where |
|---|---|
| Spot database (32 CA spots, buoy + tide registries) | `spots.json` |
| Fetchers, staleness check, live verifier | `pipeline/` |
| Tests (offline, canned API responses) | `tests/` |
| Workflows | `.github/workflows/` |

Published data lives on the **`data` branch** (one commit, replaced every run), not on `main`. Committing forecasts to `main` every hour would grow the repo by megabytes a day and leave your local copy permanently behind.

```
data branch
  index.json             spots, which buoy is live for each, 72 h outlook per spot
  meta.json              last success / error per source, attribution
  forecast/<spot>.json   hourly waves, swell trains, wind, sun (16 days)
  tides/<station>.json   highs/lows + hourly heights (ft, MLLW)
  buoys/<id>.json        latest reading + last 48 h + forecast at the buoy itself + 7-day forecast record
  skill/<id>.json        hourly buoy-vs-forecast pairs, last 7 days (carried over run to run)
  spots.json             copy of the spot database
```

### Workflows

- **CI**: ruff + pytest on every push.
- **Fetch data**: hourly (GitHub skips some scheduled runs, so hourly keeps data within a few hours); publishes to `data`. Alerts via ntfy if it fails.
- **Staleness check**: every 6 h; alerts via ntfy if any source hasn't updated.
- **Deploy app**: after every successful fetch and on app changes; publishes `app/` plus the `data` branch to GitHub Pages.
- **Send test alert**: manual button that sends one ntfy message; goes red if the secret is missing or ntfy refuses it.
- **Verify sources**: live check of every station ID and API; runs when spots or pipeline code change, and weekly. If four or more buoys stopped reporting within the same hour, it treats that as the operator's feed being delayed: spots waiting only on those buoys become warnings, and the weekly run sends one "NOAA buoy feed delayed" notice instead of a failure alert.
- **Evening digest** (`pipeline/digest.py`): about 6 PM Pacific, one ntfy message listing the spots in `alerts.json` that have a Good When to go window (peak score 0.75+) in the next 2 days; nothing is sent when nothing is Good. Triggered by cron-job.org at 18:00 America/Los_Angeles, with GitHub's schedule at 01:05 and 02:05 UTC as backup (6 PM in PDT and PST). It only sends between 5:50 and 9 PM Pacific and skips if a digest went out in the last 6 h (it asks ntfy), so backups never double up. Run workflow with **force** ticked to test it any time.
- **Mavericks Watch** (`pipeline/mavericks.py`): every 30 min (cron-job.org, GitHub schedule as backup). Idle, it only reads the published Mavericks forecast. When any hour in the next 5 days reaches the spot's `big_wave.min_ft` (15 ft) it switches on and sends one message; from then on it reads buoys 46059, 46214 and 46012 straight from NDBC and pings once when forerunners (18 s+ period, dominant or spectral swell) show at 46059, comparing that period with the forecast for 46059's own position. It stands down with a message 12 h after the last 15 ft+ forecast hour, or straight away if the forecast falls below 14 ft before the swell arrives. Its state lives on the `watch` branch (one small file; only this workflow writes it).

The scoring behind When to go exists twice: `app/js/model.js` for the app and `pipeline/score.py` (with `pipeline/sun.py`) for the digest. `tests/cases/scoring.json` holds shared cases that both `npm test` and `pytest` run, so the two can't drift apart unnoticed.

### One-time setup (GitHub website)

1. Merge this branch into `main` (scheduled workflows only run from the default branch).
2. Settings → Secrets and variables → Actions → New repository secret:
   - `NTFY_TOPIC`: your long random topic (subscribe to the same topic in the ntfy app).
   - `HEALTHCHECK_URL` (optional, recommended): a ping URL from healthchecks.io. Its free tier alerts you if pings stop, which catches the one failure the staleness check can't: GitHub's scheduler itself stopping. It can notify through ntfy.
3. Actions tab → Fetch data → Run workflow, to publish the first data.

## App

Plain HTML/CSS/JS in `app/`, no build step. GitHub Pages serves it at
`https://padraik99.github.io/wave-finder/` with the data at `./data/` on the same site.

- **Opener**: a large half wheel (NorCal · Central · SoCal) that spins: the slot pointing right is the selection, and dragging up or down turns the zones through it (it stops at the first and last zone and snaps to the nearest). Tapping a zone spins it into the slot and shows the beaches you starred there, each with current height, wind, tags (experts only, good for bodyboarding) and a one-line feature from its notes, plus the best of them right now (wave height discounted for cross and onshore wind; expert-only spots left out). Tap the zone in the slot, or Show beaches, to open its list. The wheel remembers the last zone.
- **Zone list**: that zone's spots with the current wave height, wind label and a 72 h bar strip, all from `index.json` (about 5 KB compressed). Starred spots repeat at the top. Back from a spot returns here at the same scroll position.
- **Surf / Bodyboard**: one toggle (on the opener and in each spot's When to go card, remembered) sets how spots are rated. Bodyboard mode scores punchy 2–5 ft highest and gives spots tagged `"bodyboard": true` a nudge; surf mode keeps rising to about 6 ft and falls off past 10 ft (big-wave spots excepted). Both discount cross and onshore wind (light wind forgiven) and a tide the spot doesn't like. Scoring lives in `app/js/model.js` (`hourScore`, `whenToGo`).
- **When to go**: on each spot, the best 3 daylight windows in the next 3 days, rated Good / Fair / Poor; tap one to jump the scrubber there.
- **Wetsuit hint** under water temperature (California rule of thumb).
- **Tide band** on the hour scrubber: a thin line over the hours when the tide is in the spot's preferred range (low / mid / high within that day's range).
- **Forecast record** in the live buoy panel: how far the forecast at the buoy has run from the buoy's readings over the past 7 days (needs half a day of hourly pairs before it shows).
- **Home-screen shortcuts**: long-press the app icon for NorCal, Central or SoCal.
- **Stars**: tap ☆ on a list row or a spot's header. Stars live on the phone (localStorage).
- **Alert on these** (under the starred cards on the opener): copies all your stars, and the Surf/Bodyboard mode, in the format of `alerts.json`, then links to that file on GitHub to paste over. The evening digest reads that file.
- **Near me** (top of the opener): on tap, Chrome asks for location once; the phone then ranks every spot by its score right now divided by (1 + miles / 50), within 75 mi, expert-only left out, and shows the best plus two runners-up. The position stays in the page's memory; it is never stored or sent.
- **Spot detail**: "About this spot" first (collapsible, remembered), then the hour scrubber (drag the strip, tap a day to jump to first light, or step ±1 h / ±3 h). For the chosen hour: swell trains with an in-window/blocked flag, wind as an arrow against the beach, tide height and direction, water and air temperature, first light / sunrise / sunset / last light. Live buoy panel compares the latest reading with the forecast made for the buoy's own position at that hour (wave height, period, direction, water temperature), so the gap shows how the model is doing, not how sheltered the spot is.
- **Offline**: a service worker caches the app and every data file you open. Data is network-first with an 8 s timeout, then the saved copy, with an "Offline" banner. Starred spots and the last 3 you opened are refreshed in the background while the connection is good.
- **Per refresh**: the region list costs about 5 KB; opening a spot costs about 25 to 35 KB (forecast, tide, buoy). Unchanged files come back as 304s.
- Swipe sideways (outside the scrubber), or use the buttons at the bottom, for the next or previous spot in the zone.
- A spot can carry a `big_wave` note in `spots.json` (Mavericks does), shown in the wind card when the forecast is at or above its `min_ft`.
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
