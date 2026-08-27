"""Secure API-Football profile search and season-stat normalisation."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
import threading
import time
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import requests

DIRECT_API_ROOT = "https://v3.football.api-sports.io"
RAPID_API_ROOT = "https://api-football-v1.p.rapidapi.com/v3"
CACHE_VERSION = 1
PROFILE_CACHE_TTL = 12 * 60 * 60
PLAYER_CACHE_TTL = 6 * 60 * 60
SEASONS_CACHE_TTL = 24 * 60 * 60
HTTP_TIMEOUT = (3.05, 12)
MAX_REQUEST_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 2.0
TRANSIENT_HTTP_STATUSES = frozenset({429, 502, 503, 504})

DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parent / ".footy_scout_cache" / "api-responses.json"
)
_CACHE_LOCK = threading.RLock()
LOGGER = logging.getLogger(__name__)


class FootballAPIError(RuntimeError):
    """A concise, user-facing football data error."""


def _resolved_cache_path(cache_path: str | os.PathLike[str] | None) -> Path:
    configured = os.getenv("FOOTBALLSCOUT_CACHE_PATH")
    if cache_path is not None:
        return Path(cache_path)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_CACHE_PATH


def _empty_cache() -> dict[str, Any]:
    return {"version": CACHE_VERSION, "entries": {}}


def _read_disk_cache(path: Path) -> dict[str, Any]:
    """Read the cache, treating a corrupt or incompatible file as an empty cache.

    A syntactically corrupt cache is deleted. Cache failures never prevent player
    search from reaching the provider.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_cache()
    except OSError:
        return _empty_cache()

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return _empty_cache()

    if (
        not isinstance(parsed, dict)
        or parsed.get("version") != CACHE_VERSION
        or not isinstance(parsed.get("entries"), dict)
    ):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return _empty_cache()
    return parsed


def _write_disk_cache(path: Path, cache: Mapping[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(cache, handle, ensure_ascii=False, separators=(",", ":"))
            temporary_path = Path(handle.name)
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary_path, path)
    except (OSError, TypeError, ValueError):
        try:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _cache_key(provider: str, path: str, params: Mapping[str, Any]) -> str:
    # Deliberately exclude the API key: it must never be written to disk.
    identity = json.dumps(
        {"provider": provider, "path": path, "params": dict(params)},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _cache_get(
    cache_path: Path,
    key: str,
    *,
    now: float | None = None,
    allow_stale: bool = False,
) -> dict[str, Any] | None:
    current_time = time.time() if now is None else now
    with _CACHE_LOCK:
        cache = _read_disk_cache(cache_path)
        entry = cache["entries"].get(key)
    if not isinstance(entry, Mapping):
        return None
    expires_at = _finite_number(entry.get("expires_at"))
    data = entry.get("data")
    if expires_at is None or not isinstance(data, dict):
        return None
    is_stale = expires_at <= current_time
    if is_stale and not allow_stale:
        return None
    cached = deepcopy(data)
    metadata = cached.setdefault("_meta", {})
    if not isinstance(metadata, dict):
        metadata = {}
        cached["_meta"] = metadata
    metadata["cache"] = {
        "hit": True,
        "stale": is_stale,
        "stored_at": entry.get("stored_at"),
        "expires_at": expires_at,
    }
    return cached


def _cache_set(
    cache_path: Path,
    key: str,
    data: Mapping[str, Any],
    ttl: int,
    *,
    now: float | None = None,
) -> None:
    current_time = time.time() if now is None else now
    stored_data = deepcopy(dict(data))
    metadata = stored_data.setdefault("_meta", {})
    if not isinstance(metadata, dict):
        metadata = {}
        stored_data["_meta"] = metadata
    metadata["cache"] = {
        "hit": False,
        "stored_at": current_time,
        "expires_at": current_time + max(0, int(ttl)),
    }
    with _CACHE_LOCK:
        cache = _read_disk_cache(cache_path)
        entries = cache["entries"]
        # Keep the tiny cache bounded and discard expired entries opportunistically.
        entries = {
            cache_key: entry
            for cache_key, entry in entries.items()
            if isinstance(entry, Mapping)
            and (_finite_number(entry.get("expires_at")) or 0) > current_time
        }
        if len(entries) >= 500:
            oldest = sorted(
                entries,
                key=lambda item: _finite_number(entries[item].get("stored_at")) or 0,
            )[: len(entries) - 499]
            for old_key in oldest:
                entries.pop(old_key, None)
        entries[key] = {
            "stored_at": current_time,
            "expires_at": current_time + max(0, int(ttl)),
            "data": stored_data,
        }
        cache = {"version": CACHE_VERSION, "entries": entries}
        _write_disk_cache(cache_path, cache)


def clear_disk_cache(cache_path: str | os.PathLike[str] | None = None) -> bool:
    """Delete the local football-data cache. Return whether a file was removed."""
    path = _resolved_cache_path(cache_path)
    with _CACHE_LOCK:
        existed = path.exists()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
    return existed


def get_api_credentials() -> tuple[str, str] | None:
    """Return ``(provider, key)`` from server secrets or environment variables."""
    if os.getenv("FOOTBALLSCOUT_DISABLE_API", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }:
        return None
    secret_locations = (
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    )
    secrets: Mapping[str, Any] = {}
    if any(path.is_file() for path in secret_locations):
        try:
            import streamlit as st

            secrets = st.secrets
        except (FileNotFoundError, KeyError):
            secrets = {}

    candidates = (
        ("api-sports", secrets.get("API_FOOTBALL_KEY") if secrets else None),
        ("rapidapi", secrets.get("RAPIDAPI_KEY") if secrets else None),
        ("api-sports", os.getenv("API_FOOTBALL_KEY")),
        ("rapidapi", os.getenv("RAPIDAPI_KEY")),
    )
    for provider, value in candidates:
        key = str(value).strip() if value is not None else ""
        if key:
            return provider, key
    return None


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace("%", "").strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int:
    number = _finite_number(value)
    return max(0, int(number)) if number is not None else 0


def _text(value: Any, default: str = "Unknown") -> str:
    if not isinstance(value, str):
        return default
    cleaned = value.strip()
    return cleaned or default


def _section(row: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = row.get(name)
    return section if isinstance(section, Mapping) else {}


def _display_scope(names: list[str], noun: str) -> str:
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]
    return f"{len(names)} {noun}"


def _height_cm(value: Any) -> int | None:
    number = _finite_number(str(value).split()[0] if value else None)
    return int(number) if number is not None and 120 <= number <= 230 else None


def _birth_date(value: Any) -> str | None:
    """Return a validated ISO birth date without retaining other profile details."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.isoformat() if 1900 <= parsed.year <= date.today().year else None


def age_for_season(birth_date: Any, season: str | int | None) -> int | None:
    """Return age at 31 December of the provider's season start year."""
    normalized_birth = _birth_date(birth_date)
    season_number = _finite_number(season)
    if (
        normalized_birth is None
        or season_number is None
        or not season_number.is_integer()
        or not 1900 <= season_number <= 2200
    ):
        return None
    born = date.fromisoformat(normalized_birth)
    reference = date(int(season_number), 12, 31)
    if born > reference:
        return None
    return reference.year - born.year - (
        (reference.month, reference.day) < (born.month, born.day)
    )


def _season_age(
    birth_date: Any,
    current_age: Any,
    season: str | int | None,
) -> tuple[int | None, str]:
    exact_age = age_for_season(birth_date, season)
    if exact_age is not None:
        return exact_age, "birth_date"
    age_number = _finite_number(current_age)
    season_number = _finite_number(season)
    if (
        age_number is None
        or season_number is None
        or not season_number.is_integer()
        or not 1900 <= season_number <= date.today().year
    ):
        return None, "unavailable"
    estimated = max(0, int(age_number) - (date.today().year - int(season_number)))
    return estimated, "current_age_adjusted"


def _flatten_error_detail(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        details: list[str] = []
        for key, child in value.items():
            child_details = _flatten_error_detail(child)
            if child_details:
                label = str(key).replace("_", " ").strip()
                details.extend(
                    f"{label}: {detail}" if label else detail
                    for detail in child_details
                )
        return details
    if isinstance(value, (list, tuple, set)):
        return [detail for item in value for detail in _flatten_error_detail(item)]
    if value is None or value is False or value == "":
        return []
    return [str(value)]


def _http_error_detail(response: requests.Response | None, api_key: str) -> str:
    if response is None:
        return ""
    payload: Any = None
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError, TypeError):
        text_value = getattr(response, "text", "")
        if isinstance(text_value, str) and "<html" not in text_value.casefold():
            payload = text_value

    if isinstance(payload, Mapping):
        payload = (
            payload.get("errors") or payload.get("error") or payload.get("message")
        )
    detail = "; ".join(_flatten_error_detail(payload))
    detail = " ".join(detail.split()).strip(" ;.")
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    return detail[:240]


def _quota_from_headers(headers: Any) -> dict[str, int]:
    if not isinstance(headers, Mapping):
        return {}
    lowered = {str(key).casefold(): value for key, value in headers.items()}
    quota: dict[str, int] = {}
    for label, candidates in {
        "limit": ("x-ratelimit-requests-limit", "x-ratelimit-limit"),
        "remaining": (
            "x-ratelimit-requests-remaining",
            "x-ratelimit-remaining",
        ),
    }.items():
        for candidate in candidates:
            number = _finite_number(lowered.get(candidate))
            if number is not None:
                quota[label] = max(0, int(number))
                break
    return quota


def extract_api_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return quota, paging, result-count and cache metadata from a response."""
    metadata: dict[str, Any] = {}
    raw_meta = data.get("_meta") if isinstance(data, Mapping) else None
    if isinstance(raw_meta, Mapping):
        quota = raw_meta.get("quota")
        cache = raw_meta.get("cache")
        fallback = raw_meta.get("fallback")
        if isinstance(quota, Mapping):
            metadata["quota"] = dict(quota)
        if isinstance(cache, Mapping):
            metadata["cache"] = dict(cache)
        if isinstance(fallback, Mapping):
            metadata["fallback"] = dict(fallback)

    results = _finite_number(data.get("results"))
    if results is not None:
        metadata["result_count"] = max(0, int(results))
    else:
        response = data.get("response")
        if isinstance(response, list):
            metadata["result_count"] = len(response)

    paging = data.get("paging")
    if isinstance(paging, Mapping):
        metadata["paging"] = {
            key: int(number)
            for key in ("current", "total")
            if (number := _finite_number(paging.get(key))) is not None
        }
    parameters = data.get("parameters")
    if isinstance(parameters, Mapping):
        metadata["coverage"] = {
            str(key): value
            for key, value in parameters.items()
            if str(key).casefold() not in {"key", "api_key", "token"}
        }
    return metadata


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    """Return a short bounded delay, respecting numeric Retry-After values."""
    if response is not None:
        headers = getattr(response, "headers", {})
        retry_after = headers.get("Retry-After") if isinstance(headers, Mapping) else None
        seconds = _finite_number(retry_after)
        if seconds is not None:
            return min(max(seconds, 0.0), MAX_RETRY_DELAY_SECONDS)
    return min(0.25 * (2**attempt), MAX_RETRY_DELAY_SECONDS)


def _request_with_retries(
    url: str,
    *,
    headers: Mapping[str, str],
    params: Mapping[str, Any],
) -> requests.Response:
    """Request one idempotent endpoint with bounded transient retries."""
    last_error: requests.RequestException | None = None
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            response = requests.get(
                url,
                headers=dict(headers),
                params=dict(params),
                timeout=HTTP_TIMEOUT,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(None, attempt))
            continue

        status_number = _finite_number(getattr(response, "status_code", None))
        status = int(status_number) if status_number is not None else 0
        retry_after_available = (
            status == 429
            and isinstance(getattr(response, "headers", None), Mapping)
            and "Retry-After" in response.headers
        )
        retryable_status = status in {502, 503, 504} or retry_after_available
        if retryable_status and attempt < MAX_REQUEST_ATTEMPTS - 1:
            time.sleep(_retry_delay(response, attempt))
            continue
        return response

    if last_error is not None:  # pragma: no cover - defensive loop exhaust guard
        raise last_error
    raise requests.RequestException("The football request did not complete.")


def _stale_fallback(
    cache_path: Path,
    cache_key: str,
    *,
    reason: str,
) -> dict[str, Any] | None:
    cached = _cache_get(cache_path, cache_key, allow_stale=True)
    if cached is None:
        return None
    metadata = cached.setdefault("_meta", {})
    if not isinstance(metadata, dict):
        metadata = {}
        cached["_meta"] = metadata
    metadata["fallback"] = {
        "stale": True,
        "reason": reason,
    }
    return cached


def _provider_request(
    path: str,
    params: Mapping[str, Any],
    *,
    api_key: str | None = None,
    provider: str | None = None,
    cache_ttl: int | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    if api_key is None:
        credentials = get_api_credentials()
        if credentials is None:
            raise FootballAPIError(
                "Real-player search is not configured. The site owner must add an "
                "API_FOOTBALL_KEY server secret."
            )
        provider_name, key = credentials
    else:
        key = str(api_key).strip()
        provider_name = provider or "api-sports"
    if not key:
        raise FootballAPIError("The football data key is blank.")

    if provider_name == "rapidapi":
        url = f"{RAPID_API_ROOT}/{path.lstrip('/')}"
        headers = {
            "X-RapidAPI-Key": key,
            "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
        }
    else:
        url = f"{DIRECT_API_ROOT}/{path.lstrip('/')}"
        headers = {"x-apisports-key": key}

    request_params = dict(params)
    resolved_path = _resolved_cache_path(cache_path)
    cache_key = _cache_key(provider_name, path, request_params)
    if use_cache and cache_ttl is not None and cache_ttl > 0:
        cached = _cache_get(resolved_path, cache_key)
        if cached is not None:
            LOGGER.info(
                "football_api_request provider=%s path=%s cache_hit=true",
                provider_name,
                path,
            )
            return cached

    started_at = time.monotonic()
    try:
        response = _request_with_retries(
            url,
            headers=headers,
            params=request_params,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        if use_cache and (stale := _stale_fallback(
            resolved_path, cache_key, reason="timeout"
        )) is not None:
            LOGGER.warning(
                "football_api_request provider=%s path=%s fallback=stale reason=timeout",
                provider_name,
                path,
            )
            return stale
        raise FootballAPIError("The football search timed out. Please retry.") from exc
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        if (
            use_cache
            and status in TRANSIENT_HTTP_STATUSES
            and (stale := _stale_fallback(
                resolved_path, cache_key, reason=f"http_{status}"
            ))
            is not None
        ):
            LOGGER.warning(
                "football_api_request provider=%s path=%s fallback=stale status=%s",
                provider_name,
                path,
                status,
            )
            return stale
        detail = _http_error_detail(exc.response, key)
        if status == 401:
            message = "The server's football data key was rejected (HTTP 401)."
        elif status == 403:
            detail_lower = detail.casefold()
            if any(word in detail_lower for word in ("key", "token", "auth")):
                message = "The server's football data key was rejected (HTTP 403)."
            elif any(
                phrase in detail_lower
                for phrase in (
                    "ip address",
                    "ip restriction",
                    "server ip",
                    "your ip",
                    "ip:",
                )
            ):
                message = (
                    "The football data service blocked this server's IP (HTTP 403)."
                )
            else:
                message = (
                    "The football data plan does not allow this request (HTTP 403)."
                )
        elif status == 429:
            message = "The football data daily limit has been reached (HTTP 429)."
        elif isinstance(status, int) and status >= 500:
            message = (
                f"The football data service is temporarily unavailable (HTTP {status})."
            )
        else:
            message = f"The football data request failed (HTTP {status})."
        if detail:
            message = f"{message.rstrip('.')} Provider detail: {detail}."
        raise FootballAPIError(message) from exc
    except requests.RequestException as exc:
        if use_cache and (stale := _stale_fallback(
            resolved_path, cache_key, reason="network"
        )) is not None:
            LOGGER.warning(
                "football_api_request provider=%s path=%s fallback=stale reason=network",
                provider_name,
                path,
            )
            return stale
        raise FootballAPIError("Could not reach the football data service.") from exc

    LOGGER.info(
        "football_api_request provider=%s path=%s status=%s latency_ms=%s cache_hit=false",
        provider_name,
        path,
        getattr(response, "status_code", "unknown"),
        round((time.monotonic() - started_at) * 1000),
    )

    try:
        data = response.json()
    except (requests.JSONDecodeError, ValueError) as exc:
        raise FootballAPIError(
            "The football data service returned invalid JSON."
        ) from exc
    if not isinstance(data, dict):
        raise FootballAPIError(
            "The football data service returned an unexpected format."
        )
    errors = data.get("errors")
    if errors:
        detail = "; ".join(_flatten_error_detail(errors)) or str(errors)
        detail = " ".join(detail.split()).replace(key, "[redacted]")[:240]
        raise FootballAPIError(
            f"The football data service rejected the request: {detail}"
        )
    quota = _quota_from_headers(getattr(response, "headers", {}))
    if quota:
        metadata = data.setdefault("_meta", {})
        if not isinstance(metadata, dict):
            metadata = {}
            data["_meta"] = metadata
        metadata["quota"] = quota
    if use_cache and cache_ttl is not None and cache_ttl > 0:
        metadata = data.setdefault("_meta", {})
        if not isinstance(metadata, dict):
            metadata = {}
            data["_meta"] = metadata
        now = time.time()
        metadata["cache"] = {
            "hit": False,
            "stored_at": now,
            "expires_at": now + cache_ttl,
        }
        _cache_set(resolved_path, cache_key, data, cache_ttl)
    return data


def parse_profile_response(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalise global player-profile search results."""
    responses = data.get("response") if isinstance(data, Mapping) else None
    if not isinstance(responses, list):
        raise FootballAPIError("The player search returned an unexpected format.")

    profiles: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for item in responses:
        if not isinstance(item, Mapping):
            continue
        raw_player = item.get("player")
        if not isinstance(raw_player, Mapping):
            continue
        api_id = _count(raw_player.get("id"))
        if api_id <= 0 or api_id in seen_ids:
            continue
        seen_ids.add(api_id)
        birth = raw_player.get("birth")
        birth = birth if isinstance(birth, Mapping) else {}
        profiles.append(
            {
                "api_id": api_id,
                "player_id": f"api-{api_id}",
                "name": _text(raw_player.get("name"), f"Player {api_id}"),
                "firstname": _text(raw_player.get("firstname"), ""),
                "lastname": _text(raw_player.get("lastname"), ""),
                "age": _count(raw_player.get("age")) or None,
                "birth_date": _birth_date(birth.get("date")),
                "nationality": _text(raw_player.get("nationality")),
                "height_cm": _height_cm(raw_player.get("height")),
                "position": _text(raw_player.get("position")),
                "photo": (
                    raw_player.get("photo").strip()
                    if isinstance(raw_player.get("photo"), str)
                    and raw_player.get("photo").strip()
                    else None
                ),
            }
        )
    return profiles


def _normalise_search_text(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " " for character in without_marks
        ).split()
    )


def _search_tokens(value: Any) -> list[str]:
    return _normalise_search_text(value).split()


def _search_queries(query: str) -> list[str]:
    original_tokens = query.split()
    eligible: list[tuple[str, str]] = []
    for token in original_tokens:
        normalised = _normalise_search_text(token)
        if len(normalised) >= 4:
            request_token = token if token.isascii() else normalised
            eligible.append((request_token, normalised))
    if not eligible:
        return []

    # A user's final name token is most often the surname. Work backwards at a
    # hard maximum of three requests, which also handles "Messi Lionel" safely.
    queries: list[str] = []
    seen: set[str] = set()
    for request_token, normalised in reversed(eligible):
        if normalised not in seen:
            queries.append(request_token)
            seen.add(normalised)
        if len(queries) == 3:
            break
    return queries


def _profile_search_score(profile: Mapping[str, Any], query: str) -> float:
    query_normalised = _normalise_search_text(query)
    query_tokens = set(query_normalised.split())
    name_fields = (
        _normalise_search_text(profile.get("name")),
        _normalise_search_text(profile.get("firstname")),
        _normalise_search_text(profile.get("lastname")),
    )
    combined_tokens = set(" ".join(name_fields).split())
    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & combined_tokens) / len(query_tokens)
    score = overlap * 50.0
    if query_tokens <= combined_tokens:
        score += 100.0
    if query_normalised in name_fields:
        score += 120.0
    if name_fields[2] and query_normalised == name_fields[2]:
        score += 30.0
    if name_fields[0].startswith(query_normalised):
        score += 15.0
    return score


def _profile_covers_query(profile: Mapping[str, Any], query: str) -> bool:
    query_tokens = set(_search_tokens(query))
    candidate_tokens = set(
        _search_tokens(
            " ".join(
                str(profile.get(field) or "")
                for field in ("name", "firstname", "lastname")
            )
        )
    )
    return bool(query_tokens) and query_tokens <= candidate_tokens


def filter_player_profiles(
    profiles: Iterable[Mapping[str, Any]],
    *,
    positions: Iterable[str] | str | None = None,
    nationalities: Iterable[str] | str | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
) -> list[dict[str, Any]]:
    """Filter already-normalised profiles without spending another API request."""

    def choices(value: Iterable[str] | str | None) -> set[str]:
        if value is None:
            return set()
        items = (value,) if isinstance(value, str) else value
        return {_normalise_search_text(item) for item in items if str(item).strip()}

    position_choices = choices(positions)
    nationality_choices = choices(nationalities)
    minimum = int(min_age) if min_age is not None else None
    maximum = int(max_age) if max_age is not None else None
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("min_age cannot be greater than max_age")

    filtered: list[dict[str, Any]] = []
    for profile in profiles:
        position = _normalise_search_text(profile.get("position"))
        nationality = _normalise_search_text(profile.get("nationality"))
        age_number = _finite_number(profile.get("age"))
        if position_choices and position not in position_choices:
            continue
        if nationality_choices and nationality not in nationality_choices:
            continue
        if minimum is not None and (age_number is None or age_number < minimum):
            continue
        if maximum is not None and (age_number is None or age_number > maximum):
            continue
        filtered.append(dict(profile))
    return filtered


def _search_player_profiles_with_metadata(
    query: str,
    *,
    api_key: str | None,
    provider: str | None,
    cache_path: str | os.PathLike[str] | None,
    use_cache: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cleaned_query = " ".join(str(query or "").split())
    queries = _search_queries(cleaned_query)
    if not queries:
        raise FootballAPIError(
            "Type at least 4 characters from a player's first or last name."
        )

    profiles_by_id: dict[int, dict[str, Any]] = {}
    response_metadata: list[dict[str, Any]] = []
    attempted_queries: list[str] = []
    for provider_query in queries:
        data = _provider_request(
            "players/profiles",
            {"search": provider_query},
            api_key=api_key,
            provider=provider,
            cache_ttl=PROFILE_CACHE_TTL,
            cache_path=cache_path,
            use_cache=use_cache,
        )
        attempted_queries.append(provider_query)
        response_metadata.append(extract_api_metadata(data))
        for profile in parse_profile_response(data):
            profiles_by_id.setdefault(profile["api_id"], profile)

        # A surname response includes full profile fields. Once one result covers
        # every typed token, further fallback calls would only waste quota.
        if any(
            _profile_covers_query(profile, cleaned_query)
            for profile in profiles_by_id.values()
        ):
            break

    profiles = sorted(
        profiles_by_id.values(),
        key=lambda profile: (
            -_profile_search_score(profile, cleaned_query),
            _normalise_search_text(profile.get("name")),
            profile.get("api_id", 0),
        ),
    )[:250]

    metadata: dict[str, Any] = {
        "queries": attempted_queries,
        "request_count": len(attempted_queries),
        "result_count": len(profiles),
    }
    quotas = [item.get("quota") for item in response_metadata if item.get("quota")]
    if quotas:
        last_quota = quotas[-1]
        metadata["quota"] = dict(last_quota) if isinstance(last_quota, Mapping) else {}
    cache_states = [
        bool(item.get("cache", {}).get("hit"))
        for item in response_metadata
        if isinstance(item.get("cache"), Mapping)
    ]
    if cache_states:
        metadata["all_cache_hits"] = all(cache_states)
    metadata["used_stale_fallback"] = any(
        bool(item.get("fallback", {}).get("stale"))
        for item in response_metadata
        if isinstance(item.get("fallback"), Mapping)
    )
    return profiles, metadata


def search_player_profiles(
    query: str,
    *,
    api_key: str | None = None,
    provider: str | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Search profiles by full name using at most three surname-safe requests."""
    profiles, _ = _search_player_profiles_with_metadata(
        query,
        api_key=api_key,
        provider=provider,
        cache_path=cache_path,
        use_cache=use_cache,
    )
    return profiles


def search_player_profiles_with_metadata(
    query: str,
    *,
    api_key: str | None = None,
    provider: str | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    use_cache: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return ranked profiles plus quota/cache metadata for owner diagnostics."""
    return _search_player_profiles_with_metadata(
        query,
        api_key=api_key,
        provider=provider,
        cache_path=cache_path,
        use_cache=use_cache,
    )


def parse_player_response(
    data: Mapping[str, Any], season: str | int | None = None
) -> dict[str, Any]:
    """Aggregate one real player's statistics across teams and competitions."""
    responses = data.get("response") if isinstance(data, Mapping) else None
    if not isinstance(responses, list):
        raise FootballAPIError("The season data returned an unexpected format.")
    if not responses:
        raise FootballAPIError(
            "No season statistics were found for this player. Try another season."
        )

    response = responses[0]
    if not isinstance(response, Mapping):
        raise FootballAPIError("The season data returned an unexpected format.")
    player_info = response.get("player")
    statistics = response.get("statistics")
    if not isinstance(player_info, Mapping) or not isinstance(statistics, list):
        raise FootballAPIError("The season data returned an unexpected format.")

    totals: defaultdict[str, int] = defaultdict(int)
    rating_total = 0.0
    rating_weight = 0.0
    pass_accuracy_total = 0.0
    pass_accuracy_weight = 0.0
    position_weights: defaultdict[str, float] = defaultdict(float)
    teams: list[str] = []
    competitions: list[str] = []
    competition_ids: set[tuple[str, str]] = set()
    clean_sheets_total = 0
    clean_sheets_available = False
    valid_rows = 0

    for row_index, row in enumerate(statistics):
        if not isinstance(row, Mapping):
            continue
        games = _section(row, "games")
        goals = _section(row, "goals")
        tackles = _section(row, "tackles")
        shots = _section(row, "shots")
        passes = _section(row, "passes")
        duels = _section(row, "duels")
        if not games:
            continue
        valid_rows += 1

        appearances = _count(games.get("appearences"))
        minutes = _count(games.get("minutes"))
        totals["games"] += appearances
        totals["starts"] += _count(games.get("lineups"))
        totals["minutes"] += minutes
        totals["goals"] += _count(goals.get("total"))
        totals["assists"] += _count(goals.get("assists"))
        totals["conceded"] += _count(goals.get("conceded"))
        totals["saves"] += _count(goals.get("saves"))
        totals["tackles"] += _count(tackles.get("total"))
        totals["interceptions"] += _count(tackles.get("interceptions"))
        totals["shots"] += _count(shots.get("total"))
        totals["key_passes"] += _count(passes.get("key"))
        totals["duels_total"] += _count(duels.get("total"))
        totals["duels_won"] += _count(duels.get("won"))

        weight = float(minutes or appearances or 1)
        rating = _finite_number(games.get("rating"))
        if rating is not None:
            rating_total += min(max(rating, 0.0), 10.0) * weight
            rating_weight += weight
        pass_accuracy = _finite_number(passes.get("accuracy"))
        if pass_accuracy is not None:
            pass_accuracy_total += min(max(pass_accuracy, 0.0), 100.0) * weight
            pass_accuracy_weight += weight

        position = _text(games.get("position"))
        if position != "Unknown":
            position_weights[position] += weight

        team_name = _text(_section(row, "team").get("name"))
        if team_name != "Unknown" and team_name not in teams:
            teams.append(team_name)
        league = _section(row, "league")
        league_name = _text(league.get("name"))
        if league_name != "Unknown" and league_name not in competitions:
            competitions.append(league_name)
        league_id = league.get("id")
        if league_id is not None:
            competition_ids.add(("id", str(league_id)))
        elif league_name != "Unknown":
            competition_ids.add(("name", league_name.casefold()))
        else:
            competition_ids.add(("row", str(row_index)))

        for field in ("cleansheets", "clean_sheets"):
            if field in games and _finite_number(games.get(field)) is not None:
                clean_sheets_available = True
                clean_sheets_total += _count(games.get(field))
                break

    if valid_rows == 0:
        raise FootballAPIError("No usable season statistics were returned.")

    api_id = _count(player_info.get("id"))
    birth = player_info.get("birth")
    birth = birth if isinstance(birth, Mapping) else {}
    birth_date = _birth_date(birth.get("date"))
    age, age_source = _season_age(birth_date, player_info.get("age"), season)
    position = (
        max(position_weights, key=position_weights.get)
        if position_weights
        else _text(player_info.get("position"))
    )
    season_label = str(season or "Unknown")
    scope = (
        competitions[0]
        if valid_rows == 1 and len(competitions) == 1
        else "All teams and competitions"
    )
    duels_won_pct = (
        round(totals["duels_won"] / totals["duels_total"] * 100.0, 1)
        if totals["duels_total"]
        else None
    )

    return {
        "api_id": api_id,
        "player_id": f"api-{api_id}",
        "name": _text(player_info.get("name")),
        "photo": (
            player_info.get("photo").strip()
            if isinstance(player_info.get("photo"), str)
            and player_info.get("photo").strip()
            else None
        ),
        "age": age,
        "birth_date": birth_date,
        "age_source": age_source,
        "age_reference": (
            f"{season_label}-12-31" if season_label != "Unknown" else None
        ),
        "nationality": _text(player_info.get("nationality")),
        "preferred_foot": None,
        "height_cm": _height_cm(player_info.get("height")),
        "team": _display_scope(teams, "teams"),
        "league": _display_scope(competitions, "competitions"),
        "teams": teams,
        "competitions": competitions,
        "position": position,
        "position_detail": position,
        "games": totals["games"],
        "starts": totals["starts"],
        "minutes": totals["minutes"],
        "rating": round(rating_total / rating_weight, 2) if rating_weight else None,
        "scope": scope,
        "season": season_label,
        "competition_count": max(1, len(competition_ids)),
        "contract_years": None,
        "contract_expires": None,
        # The provider's injury flag describes the current profile, not the
        # requested historical season, so it must not influence past valuations.
        "injury_risk": "Unknown",
        "games_missed_365": None,
        "league_strength": None,
        "club_selling_power": None,
        "recent_fee": None,
        "form": [],
        "data_source": "api_football",
        "dataset_version": "live",
        "api_metadata": extract_api_metadata(data),
        "goals": totals["goals"],
        "assists": totals["assists"],
        "conceded": totals["conceded"],
        "saves": totals["saves"],
        "tackles": totals["tackles"],
        "interceptions": totals["interceptions"],
        "clean_sheets": clean_sheets_total if clean_sheets_available else None,
        "shots": totals["shots"],
        "key_passes": totals["key_passes"],
        "xg": None,
        "xa": None,
        "pass_accuracy": (
            round(pass_accuracy_total / pass_accuracy_weight, 1)
            if pass_accuracy_weight
            else None
        ),
        "duels_won_pct": duels_won_pct,
        "aerials_won_pct": None,
        # API-Football does not expose this field in the standard player response.
        # Keep it missing so the interface shows “—” rather than a false zero.
        "progressive_actions": None,
    }


def parse_seasons_response(data: Mapping[str, Any]) -> list[int]:
    """Normalise the provider's available-season list, newest first."""
    responses = data.get("response") if isinstance(data, Mapping) else None
    if not isinstance(responses, list):
        raise FootballAPIError("The available seasons returned an unexpected format.")
    seasons: set[int] = set()
    for value in responses:
        number = _finite_number(value)
        if number is not None and number.is_integer() and 1900 <= number <= 2100:
            seasons.add(int(number))
    return sorted(seasons, reverse=True)


def parse_account_status(data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize subscription and quota status without retaining account PII."""
    response = data.get("response") if isinstance(data, Mapping) else None
    if not isinstance(response, Mapping):
        raise FootballAPIError("The account status returned an unexpected format.")
    subscription = response.get("subscription")
    requests_status = response.get("requests")
    subscription = subscription if isinstance(subscription, Mapping) else {}
    requests_status = requests_status if isinstance(requests_status, Mapping) else {}
    current = _finite_number(requests_status.get("current"))
    limit_day = _finite_number(requests_status.get("limit_day"))
    return {
        "plan": _text(subscription.get("plan"), "Unknown"),
        "active": subscription.get("active") is True,
        "requests_current": max(0, int(current)) if current is not None else None,
        "requests_limit": max(0, int(limit_day)) if limit_day is not None else None,
    }


def fetch_account_status(
    *,
    api_key: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return plan/quota status; the provider documents this call as quota-free."""
    # Do not persist the raw response because it includes the owner's account PII.
    data = _provider_request(
        "status",
        {},
        api_key=api_key,
        provider=provider,
        use_cache=False,
    )
    return parse_account_status(data)


def _normalise_optional_player_id(player_id: int | str | None) -> int | None:
    if player_id is None:
        return None
    try:
        normalised_id = int(str(player_id).strip())
    except (TypeError, ValueError, OverflowError) as exc:
        raise FootballAPIError("Player ID must be a positive integer.") from exc
    if normalised_id <= 0:
        raise FootballAPIError("Player ID must be a positive integer.")
    return normalised_id


def fetch_available_seasons_with_metadata(
    player_id: int | str | None = None,
    *,
    api_key: str | None = None,
    provider: str | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    use_cache: bool = True,
) -> tuple[list[int], dict[str, Any]]:
    """Fetch provider-wide seasons, or only seasons available for one player."""
    normalised_id = _normalise_optional_player_id(player_id)
    params = {"player": normalised_id} if normalised_id is not None else {}
    data = _provider_request(
        "players/seasons",
        params,
        api_key=api_key,
        provider=provider,
        cache_ttl=SEASONS_CACHE_TTL,
        cache_path=cache_path,
        use_cache=use_cache,
    )
    seasons = parse_seasons_response(data)
    metadata = extract_api_metadata(data)
    metadata["season_count"] = len(seasons)
    if normalised_id is not None:
        metadata["player_id"] = normalised_id
    return seasons, metadata


def fetch_available_seasons(
    player_id: int | str | None = None,
    *,
    api_key: str | None = None,
    provider: str | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    use_cache: bool = True,
) -> list[int]:
    """Return available seasons, optionally limited to a player ID."""
    seasons, _ = fetch_available_seasons_with_metadata(
        player_id,
        api_key=api_key,
        provider=provider,
        cache_path=cache_path,
        use_cache=use_cache,
    )
    return seasons


def fetch_player_stats(
    player_id: int,
    season: str | int = "2025",
    *,
    api_key: str | None = None,
    provider: str | None = None,
    cache_path: str | os.PathLike[str] | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Fetch and normalise one real player's season statistics."""
    normalised_id = _normalise_optional_player_id(player_id)
    assert normalised_id is not None
    season_text = str(season).strip()
    if len(season_text) != 4 or not season_text.isdigit():
        raise FootballAPIError("Season must be a four-digit start year.")
    data = _provider_request(
        "players",
        {"id": normalised_id, "season": season_text},
        api_key=api_key,
        provider=provider,
        cache_ttl=PLAYER_CACHE_TTL,
        cache_path=cache_path,
        use_cache=use_cache,
    )
    return parse_player_response(data, season=season_text)
