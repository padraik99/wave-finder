"""Paths and constants shared by the pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOTS_FILE = ROOT / "spots.json"

USER_AGENT = (
    "wave-finder/0.1 (personal, non-commercial surf app; "
    "https://github.com/padraik99/wave-finder)"
)

# All forecast timestamps are unix seconds (UTC). Daily buckets (sunrise/sunset)
# use California local days.
LOCAL_TZ = "America/Los_Angeles"

FORECAST_DAYS = 16
# Forecast point used when a spot doesn't set one: this far offshore along the
# direction the beach faces, so the marine model samples water, not land.
DEFAULT_OFFSHORE_KM = 3.0

# A buoy counts as live if its latest observation is newer than this.
BUOY_LIVE_HOURS = 6.0
# Hours of buoy history kept in the published JSON.
BUOY_HISTORY_HOURS = 48

ATTRIBUTION = [
    "Weather and marine forecasts: Open-Meteo.com (CC BY 4.0), using models from "
    "ECMWF, NOAA, DWD and Meteo-France.",
    "Tide predictions: NOAA CO-OPS.",
    "Buoy observations: NOAA National Data Buoy Center; CDIP buoys operated by "
    "Scripps Institution of Oceanography, distributed via NDBC.",
]
