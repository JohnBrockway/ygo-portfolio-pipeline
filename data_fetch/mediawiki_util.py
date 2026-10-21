"""
Shared plumbing for talking to the Yugipedia (MediaWiki) API: session and User-Agent,
rate limiting, retries, and following the paging tokens. Every fetcher (cards, sets, ...)
goes through here so the etiquette and error handling live in one place.
"""
import os
import time

import requests
from dotenv import load_dotenv

API_URL = "https://yugipedia.com/api.php"
EMAIL_KEY = "USER_AGENT_EMAIL"

# Yugipedia asks for a descriptive User-Agent with contact info, and at most one
# request per second. The limit is enforced across ALL requests in the process,
# not just between pages of one query.
DELAY_SECONDS = 1.0

RETRY_STATUSES = {429, 500, 502, 503, 504, 520}
MAX_ATTEMPTS = 5

# Every request here is an action=query. formatversion 2 gives clean JSON
# (pages as a list, booleans as booleans). Callers can override any of these.
DEFAULT_PARAMS = {
    "action": "query",
    "format": "json",
    "formatversion": "2",
}

_last_request_time = 0.0


def make_session():
    """A requests session whose User-Agent carries the contact email Yugipedia asks for."""
    load_dotenv()
    email = os.getenv(EMAIL_KEY)
    if not email:
        raise SystemExit(f"Set {EMAIL_KEY} in your environment or .env so the User-Agent has contact info.")
    session = requests.Session()
    session.headers["User-Agent"] = f"yugioh-collection-tracker/0.1 (contact: {email})"
    return session


def _throttle():
    """Sleep as needed so requests start at least DELAY_SECONDS apart, process-wide."""
    global _last_request_time
    wait = DELAY_SECONDS - (time.monotonic() - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.monotonic()


def _backoff_delay(attempt):
    """Exponential backoff for attempt 0, 1, 2, ...: 1s, 2s, 4s, 8s, 16s."""
    return 2.0 ** attempt


def _retry_delay(response, attempt):
    """How long to wait before retrying: the server's Retry-After if it's a number of seconds, else backoff.

    Retry-After can also be an HTTP date, which float() rejects, so that case uses backoff too.
    """
    try:
        return float(response.headers.get("Retry-After", ""))
    except ValueError:
        return _backoff_delay(attempt)


def _get(session, params):
    """One API call: throttled, retried on 429/5xx/network errors, API errors raised."""
    for attempt in range(MAX_ATTEMPTS):
        _throttle()
        attempt_label = f"attempt {attempt + 1}/{MAX_ATTEMPTS} failed"

        try:
            response = session.get(API_URL, params=params, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as error:
            delay = _backoff_delay(attempt)
            print(f"{attempt_label}: network error ({error}); waiting {delay:.0f}s")
            time.sleep(delay)
            continue

        if response.status_code in RETRY_STATUSES:
            delay = _retry_delay(response, attempt)
            print(f"{attempt_label}: HTTP {response.status_code}; waiting {delay:.0f}s")
            time.sleep(delay)
            continue

        response.raise_for_status()
        data = response.json()
        if "error" in data:
            # MediaWiki reports bad requests as HTTP 200 with an "error" object.
            raise RuntimeError(f"MediaWiki API error: {data['error']}")
        return data
    raise RuntimeError(f"giving up after {MAX_ATTEMPTS} attempts: {params}")


def query(session, params, max_requests=None):
    """Yield each API response for a query, following the API's paging tokens."""
    params = {**DEFAULT_PARAMS, **params}
    requests_made = 0
    while True:
        data = _get(session, params)
        requests_made += 1

        if "warnings" in data:
            print("API warnings:", data["warnings"])

        yield data

        if "continue" not in data:
            break
        if max_requests and requests_made >= max_requests:
            break
        params.update(data["continue"])


def query_pages(session, params, max_requests=None):
    """Like query(), but yield the individual pages (for generator=... queries)."""
    for requests_made, data in enumerate(query(session, params, max_requests), start=1):
        # An empty category comes back with no "query" key at all.
        pages = data.get("query", {}).get("pages", [])
        print(f"request {requests_made}: {len(pages)} pages")
        yield from pages
