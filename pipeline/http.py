"""HTTP session with retries and a descriptive User-Agent."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import USER_AGENT

TIMEOUT = 30


class FetchError(RuntimeError):
    """A source returned an error or data we can't use."""


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def get_json(session, url: str, params: dict | None = None):
    resp = session.get(url, params=params, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise FetchError(f"{url} returned HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise FetchError(f"{url} returned non-JSON: {resp.text[:300]}") from exc


def get_text(session, url: str, params: dict | None = None) -> str:
    resp = session.get(url, params=params, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise FetchError(f"{url} returned HTTP {resp.status_code}")
    return resp.text
