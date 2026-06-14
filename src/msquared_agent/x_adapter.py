import os
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .app_log import log_event
from .approval_queue import add_to_queue
from .approval_queue import get_approval_item, mark_sent_or_posted
from .audit_store import log_action
from .claim_guard import check_claims
from .env_loader import get_env, load_env_file, save_env_values
from .intake_store import add_intake_item
from .settings import feature_enabled


X_API_BASE = "https://api.x.com"
TRANSIENT_X_STATUSES = {408, 409, 429, 500, 502, 503, 504}
PAYMENT_REQUIRED_HELP = (
    "X API returned 402 Payment Required. This usually means the current X API project plan "
    "does not include the requested endpoint. Use the numeric X user id to avoid handle lookup, "
    "and check that your plan includes user lookup, mentions, and recent search."
)
UNAUTHORIZED_HELP = (
    "X API returned 401 Unauthorized. Check that the saved OAuth 2.0 access token is a user-context "
    "token for the MSquared account, not the app-only bearer token; that it was issued after the app "
    "permissions were set to Read and write; that the scopes include users.read, tweet.read, tweet.write, "
    "and offline.access; and that the refresh token is present so the app can renew expired access tokens."
)
APP_BEARER_UNAUTHORIZED_HELP = (
    "X API returned 401 Unauthorized for the app-only credential. Copy the current app-only value from "
    "the X Developer Portal App-Only Authentication section into the app-only field in Admin, then save settings. "
    "If you regenerated the app-only credential in X, the old value in .env is immediately invalid."
)


def fetch_x_feed(config: dict | None = None) -> list:
    """Fetch monitored X items.

    Phase 0 works with local/operator-supplied items. If ENABLE_X_READ is true
    and a bearer token is configured, this can read recent matching public posts.
    It never creates auto-reply approvals from keyword search results.
    """
    config = config or {}
    load_env_file()
    items = []

    local_items = config.get("items") or []
    log_event(
        "x_fetch_started",
        "info",
        "X refresh started.",
        {"local_item_count": len(local_items)},
    )
    for item in local_items:
        items.append(add_intake_item({
            "channel": "x",
            "source_type": item.get("source_type", "x_monitor"),
            "source_id": item.get("id") or item.get("source_id"),
            "author": item.get("author", ""),
            "text": item.get("text", ""),
            "url": item.get("url", ""),
        }))

    if not feature_enabled("ENABLE_X_READ"):
        log_event(
            "x_fetch_skipped",
            "info",
            "X API read is disabled. Imported local/operator-supplied items only.",
            {"imported_count": len(items), "reason": "ENABLE_X_READ=false"},
        )
        return items

    bearer_token = _x_api_bearer_token(config)
    auth_mode = _x_read_auth_mode(config, bearer_token)
    query = config.get("query") if "query" in config else get_env("X_MONITOR_QUERY") or "DIIaC OR MSquared OR governed decision intelligence"
    monitor_user_id = config.get("monitor_user_id") if "monitor_user_id" in config else get_env("X_MONITOR_USER_ID")
    if not bearer_token and _has_oauth2_refresh_token(config):
        try:
            bearer_token = refresh_oauth2_access_token(config)
            auth_mode = "oauth2_user"
        except Exception as exc:
            log_event(
                "x_oauth2_refresh_failed",
                "warning",
                "OAuth 2.0 token refresh failed before X refresh; app bearer or new generated user tokens are required.",
                {"error": str(exc), "http_status": _http_status(exc)},
            )
    if not bearer_token:
        log_event(
            "x_fetch_skipped",
            "warning",
            "X API read is enabled but no app bearer token, OAuth 2.0 access token, or refresh token is configured.",
            {"imported_count": len(items), "reason": "X OAuth token missing"},
        )
        log_action({
            "action": "x_feed_fetch_skipped",
            "channel": "x",
            "final_action_status": "skipped",
            "reason": "X OAuth token missing",
        })
        return items

    try:
        http_get = config.get("http_get") or requests.get
        mention_count, search_count, source_errors = _fetch_x_feed_with_token(
            items,
            bearer_token,
            auth_mode,
            monitor_user_id,
            query,
            config,
            http_get,
        )
        _raise_if_x_sources_failed(items, mention_count, search_count, source_errors)
        _log_x_source_warnings(source_errors)
        log_event(
            "x_fetch_complete",
            "info",
            "X refresh completed.",
            {
                "imported_count": len(items),
                "mention_count": mention_count,
                "search_count": search_count,
                "monitor_user_id_configured": bool(monitor_user_id),
                "query_configured": bool(query),
            },
        )
    except Exception as exc:
        if _is_unauthorized(exc) and _has_oauth2_refresh_token(config):
            try:
                refreshed_token = refresh_oauth2_access_token(config)

                http_get = config.get("http_get") or requests.get
                mention_count, search_count, source_errors = _fetch_x_feed_with_token(
                    items,
                    refreshed_token,
                    "oauth2_user",
                    monitor_user_id,
                    query,
                    config,
                    http_get,
                )
                _raise_if_x_sources_failed(items, mention_count, search_count, source_errors)
                _log_x_source_warnings(source_errors)
                log_event(
                    "x_fetch_complete",
                    "info",
                    "X refresh completed after refreshing OAuth 2.0 access token.",
                    {
                        "imported_count": len(items),
                        "mention_count": mention_count,
                        "search_count": search_count,
                        "monitor_user_id_configured": bool(monitor_user_id),
                        "query_configured": bool(query),
                    },
                )
                return items
            except Exception as refresh_exc:
                log_event(
                    "x_oauth2_refresh_failed",
                    "error",
                    "OAuth 2.0 token refresh failed during X refresh.",
                    {"error": str(refresh_exc)},
                )
        log_event(
            "x_fetch_failed",
            "error",
            _x_failure_message(exc, auth_mode=auth_mode),
            {"error": str(exc), "http_status": _http_status(exc), "imported_count": len(items)},
        )
        log_action({
            "action": "x_feed_fetch_failed",
            "channel": "x",
            "final_action_status": "failed",
            "error": str(exc),
        })

    return items


def _fetch_x_feed_with_token(items, bearer_token, auth_mode, monitor_user_id, query, config, http_get) -> tuple[int, int, list[dict]]:
    headers = {"Authorization": f"Bearer {bearer_token}"}
    mention_count = 0
    search_count = 0
    source_errors = []
    if monitor_user_id:
        try:
            resolved_user_id = _resolve_x_user_id(monitor_user_id, headers, http_get)
            response = _x_get_with_retry(
                http_get,
                f"{X_API_BASE}/2/users/{resolved_user_id}/mentions",
                params={
                    "max_results": config.get("max_results", 10),
                    "tweet.fields": "author_id,created_at,conversation_id",
                },
                headers=headers,
                timeout=20,
            )
            for tweet in response.json().get("data", []):
                items.append(_add_x_tweet(tweet, "x_mention"))
                mention_count += 1
        except Exception as exc:
            source_errors.append({"source": "mentions", "exception": exc, "auth_mode": auth_mode})

    if query:
        try:
            response = _x_get_with_retry(
                http_get,
                f"{X_API_BASE}/2/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": config.get("max_results", 10),
                    "tweet.fields": "author_id,created_at,conversation_id",
                },
                headers=headers,
                timeout=20,
            )
            for tweet in response.json().get("data", []):
                items.append(_add_x_tweet(tweet, "x_monitor"))
                search_count += 1
        except Exception as exc:
            source_errors.append({"source": "recent_search", "exception": exc, "auth_mode": auth_mode})
    return mention_count, search_count, source_errors


def _raise_if_x_sources_failed(items: list, mention_count: int, search_count: int, source_errors: list[dict]) -> None:
    if source_errors and mention_count == 0 and search_count == 0 and not items:
        raise source_errors[0]["exception"]


def _log_x_source_warnings(source_errors: list[dict]) -> None:
    for error in source_errors:
        exc = error["exception"]
        log_event(
            "x_fetch_source_failed",
            "warning",
            f"X {error['source']} source failed while other intake may still be available. {_x_failure_message(exc, auth_mode=error.get('auth_mode', ''))}",
            {"source": error["source"], "http_status": _http_status(exc), "error": str(exc)},
        )


def _x_api_bearer_token(config: dict) -> str | None:
    return (
        config.get("bearer_token")
        or get_env("X_BEARER_TOKEN")
        or config.get("oauth2_access_token")
        or get_env("X_OAUTH2_ACCESS_TOKEN")
    )


def _x_read_auth_mode(config: dict, token: str | None) -> str:
    if not token:
        return "missing"
    app_bearer = config.get("bearer_token") or get_env("X_BEARER_TOKEN")
    if app_bearer and token == app_bearer:
        return "app_bearer"
    return "oauth2_user"


def _has_oauth2_refresh_token(config: dict) -> bool:
    return bool(config.get("oauth2_refresh_token") or get_env("X_OAUTH2_REFRESH_TOKEN"))


def _has_oauth1_user_credentials(config: dict) -> bool:
    return all([
        config.get("consumer_key") or get_env("X_CONSUMER_KEY") or get_env("X_API_KEY"),
        config.get("consumer_secret") or get_env("X_CONSUMER_SECRET") or get_env("X_API_SECRET"),
        config.get("access_token") or get_env("X_ACCESS_TOKEN"),
        config.get("access_token_secret") or get_env("X_ACCESS_TOKEN_SECRET"),
    ])


def _is_unauthorized(exc: Exception) -> bool:
    return _http_status(exc) == 401 or "401" in str(exc)


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(response, "status", None)
    if status:
        return int(status)
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status:
        return int(status)
    text = str(exc)
    for candidate in (400, 401, 402, 403, 404, 408, 409, 429, 500, 502, 503, 504):
        if str(candidate) in text:
            return candidate
    return None


def _x_failure_message(exc: Exception, auth_mode: str = "") -> str:
    if _http_status(exc) == 402:
        return PAYMENT_REQUIRED_HELP
    if _http_status(exc) == 401:
        detail = _x_error_detail(exc)
        help_text = APP_BEARER_UNAUTHORIZED_HELP if auth_mode == "app_bearer" else UNAUTHORIZED_HELP
        return f"{help_text} Provider detail: {detail}" if detail else help_text
    if _http_status(exc) == 403:
        return "X refresh failed with 403 Forbidden. Check X app permissions, OAuth scopes, and endpoint access."
    if _http_status(exc) == 429:
        return "X refresh failed because the X API rate limit was exceeded."
    return "X refresh failed. Check X credentials, permissions, rate limits, and monitor settings."


def _x_error_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        payload = response.json()
    except Exception:
        return str(getattr(response, "text", "") or "")[:320]

    parts = []
    for key in ("title", "detail", "type"):
        if payload.get(key):
            parts.append(str(payload[key]))
    for error in payload.get("errors", []) if isinstance(payload.get("errors"), list) else []:
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or error.get("title")
            if message:
                parts.append(str(message))
    return " | ".join(parts)[:320]


def _is_transient_x_exception(exc: Exception) -> bool:
    if _http_status(exc) in TRANSIENT_X_STATUSES:
        return True
    return isinstance(exc, (requests.Timeout, requests.ConnectionError))


def _log_x_retry(retry_state) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log_event(
        "x_api_retry",
        "warning",
        "Transient X API failure; retrying request.",
        {
            "attempt": retry_state.attempt_number,
            "http_status": _http_status(exc) if exc else None,
            "error": str(exc) if exc else "",
        },
    )


@retry(
    retry=retry_if_exception(_is_transient_x_exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    before_sleep=_log_x_retry,
    reraise=True,
)
def _x_get_with_retry(http_get, url: str, **kwargs):
    response = http_get(url, **kwargs)
    response.raise_for_status()
    return response


@retry(
    retry=retry_if_exception(_is_transient_x_exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    before_sleep=_log_x_retry,
    reraise=True,
)
def _x_post_with_retry(http_post, url: str, **kwargs):
    response = http_post(url, **kwargs)
    response.raise_for_status()
    return response


@retry(
    retry=retry_if_exception(_is_transient_x_exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    before_sleep=_log_x_retry,
    reraise=True,
)
def _create_tweet_with_retry(client, kwargs: dict, user_auth=None):
    if user_auth is None:
        return client.create_tweet(**kwargs)
    return client.create_tweet(user_auth=user_auth, **kwargs)


def _post_tweet_with_oauth2(payload_json: dict, access_token: str, http_post=None) -> dict:
    response = _x_post_with_retry(
        http_post or requests.post,
        f"{X_API_BASE}/2/tweets",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload_json,
        timeout=20,
    )
    payload = response.json()
    return payload.get("data") or payload


def refresh_oauth2_access_token(config: dict | None = None) -> str:
    config = config or {}
    refresh_token = config.get("oauth2_refresh_token") or get_env("X_OAUTH2_REFRESH_TOKEN")
    client_id = config.get("client_id") or get_env("X_CLIENT_ID")
    client_secret = config.get("client_secret") or get_env("X_CLIENT_SECRET")
    if not refresh_token:
        raise RuntimeError("X_OAUTH2_REFRESH_TOKEN is missing.")
    if not client_id:
        raise RuntimeError("X_CLIENT_ID is required to refresh OAuth 2.0 tokens.")

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if client_secret:
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"
    else:
        data["client_id"] = client_id

    response = _x_post_with_retry(
        requests.post,
        "https://api.x.com/2/oauth2/token",
        headers=headers,
        data=data,
        timeout=20,
    )
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("OAuth 2.0 refresh response did not include an access token.")

    expires_at = ""
    if payload.get("expires_in"):
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))).isoformat()

    saved_values = {
        "X_OAUTH2_ACCESS_TOKEN": access_token,
        "X_OAUTH2_REFRESH_TOKEN": payload.get("refresh_token") or refresh_token,
        "X_OAUTH2_ACCESS_TOKEN_EXPIRES_AT": expires_at,
        "X_OAUTH2_SCOPE": payload.get("scope", ""),
    }
    save_env_values(saved_values)
    log_event(
        "x_oauth2_token_refreshed",
        "info",
        "OAuth 2.0 access token refreshed and saved.",
        {"expires_at": expires_at, "scope_configured": bool(saved_values["X_OAUTH2_SCOPE"])},
    )
    return access_token


def _resolve_x_user_id(value: str, headers: dict, http_get) -> str:
    reference = str(value).strip()
    if reference.isdigit():
        return reference

    username = reference.lstrip("@").strip()
    if not username:
        raise ValueError("X monitor user id or handle is blank.")

    response = _x_get_with_retry(
        http_get,
        f"{X_API_BASE}/2/users/by/username/{quote(username)}",
        params={"user.fields": "id,username"},
        headers=headers,
        timeout=20,
    )
    data = response.json().get("data") or {}
    resolved = str(data.get("id", "")).strip()
    if not resolved.isdigit():
        raise ValueError(f"Could not resolve X handle @{username} to a numeric user id.")
    log_event(
        "x_user_resolved",
        "info",
        "Resolved X handle to numeric user id for mentions monitoring.",
        {"username": username, "resolved_user_id": resolved},
    )
    return resolved


def test_x_connection(config: dict | None = None) -> dict:
    """Run a read-only X auth diagnostic without posting or sending."""
    config = config or {}
    load_env_file()
    http_get = config.get("http_get") or requests.get
    oauth2_access_token = config.get("oauth2_access_token") or get_env("X_OAUTH2_ACCESS_TOKEN")
    app_bearer_token = config.get("bearer_token") or get_env("X_BEARER_TOKEN")
    monitor_user_id = config.get("monitor_user_id") if "monitor_user_id" in config else get_env("X_MONITOR_USER_ID")
    checks = []

    if app_bearer_token:
        auth_mode = "app_bearer"
        headers = {"Authorization": f"Bearer {app_bearer_token}"}
        if not monitor_user_id:
            message = "App bearer token is configured, but no X_MONITOR_USER_ID is set for a read-only validation call."
            log_event("x_connection_test_failed", "warning", message, {"auth_mode": auth_mode})
            return {"ok": False, "auth_mode": auth_mode, "message": message, "http_status": None, "checks": checks}
        try:
            resolved_user_id = _resolve_x_user_id(monitor_user_id, headers, http_get)
            response = _x_get_with_retry(
                http_get,
                f"{X_API_BASE}/2/users/{resolved_user_id}",
                params={"user.fields": "id,username"},
                headers=headers,
                timeout=20,
            )
            data = response.json().get("data") or {}
            checks.append({
                "name": "monitor_user_lookup",
                "ok": True,
                "user_id": str(data.get("id") or resolved_user_id),
                "username": str(data.get("username", "")),
            })
            log_event("x_connection_test_complete", "info", "X app bearer connection test completed.", {"auth_mode": auth_mode})
            return {
                "ok": True,
                "auth_mode": auth_mode,
                "message": f"X app bearer token can read the monitor user {data.get('username') or resolved_user_id}.",
                "http_status": 200,
                "checks": checks,
            }
        except Exception as exc:
            if not oauth2_access_token and not _has_oauth2_refresh_token(config):
                return _x_connection_result(False, auth_mode, checks, exc)
            checks.append({
                "name": "app_bearer_read",
                "ok": False,
                "http_status": _http_status(exc),
                "message": _x_failure_message(exc, auth_mode=auth_mode),
            })

    if not oauth2_access_token and _has_oauth2_refresh_token(config):
        oauth2_access_token = refresh_oauth2_access_token(config)
        checks.append({"name": "oauth2_refresh", "ok": True})

    if oauth2_access_token:
        headers = {"Authorization": f"Bearer {oauth2_access_token}"}
        auth_mode = "oauth2_user"
        try:
            response = _x_get_with_retry(
                http_get,
                f"{X_API_BASE}/2/users/me",
                params={"user.fields": "id,username"},
                headers=headers,
                timeout=20,
            )
        except Exception as exc:
            if not _is_unauthorized(exc) or not _has_oauth2_refresh_token(config):
                return _x_connection_result(False, auth_mode, checks, exc)
            oauth2_access_token = refresh_oauth2_access_token(config)
            headers = {"Authorization": f"Bearer {oauth2_access_token}"}
            try:
                response = _x_get_with_retry(
                    http_get,
                    f"{X_API_BASE}/2/users/me",
                    params={"user.fields": "id,username"},
                    headers=headers,
                    timeout=20,
                )
                checks.append({"name": "oauth2_refresh_after_401", "ok": True})
            except Exception as refresh_exc:
                return _x_connection_result(False, auth_mode, checks, refresh_exc)

        data = response.json().get("data") or {}
        checks.append({
            "name": "authenticated_user",
            "ok": True,
            "user_id": str(data.get("id", "")),
            "username": str(data.get("username", "")),
        })
        log_event("x_connection_test_complete", "info", "X OAuth 2.0 connection test completed.", {"auth_mode": auth_mode})
        return {
            "ok": True,
            "auth_mode": auth_mode,
            "message": f"X OAuth 2.0 user-context token is valid for @{data.get('username', 'unknown')}.",
            "http_status": 200,
            "checks": checks,
        }

    message = "No X OAuth 2.0 access token, refresh token, or app bearer token is configured."
    log_event("x_connection_test_failed", "warning", message, {"auth_mode": "missing"})
    return {"ok": False, "auth_mode": "missing", "message": message, "http_status": None, "checks": checks}


def _x_connection_result(ok: bool, auth_mode: str, checks: list[dict], exc: Exception) -> dict:
    message = _x_failure_message(exc, auth_mode=auth_mode)
    result = {
        "ok": ok,
        "auth_mode": auth_mode,
        "message": message,
        "http_status": _http_status(exc),
        "provider_detail": _x_error_detail(exc),
        "checks": checks,
    }
    log_event(
        "x_connection_test_failed",
        "warning",
        "X connection test failed.",
        {"auth_mode": auth_mode, "http_status": result["http_status"], "message": message},
    )
    return result


def _x_post_failure_message(exc: Exception, auth_mode: str) -> str:
    status = _http_status(exc)
    detail = _x_error_detail(exc) or str(exc)
    detail_suffix = f" Provider detail: {detail}" if detail else ""
    if auth_mode == "oauth1a_user" and status == 403:
        return (
            "X post failed with OAuth 1.0a app permissions. The app or OAuth 1.0a access token is not write-enabled "
            "for /2/tweets. Prefer OAuth 2.0 user-context posting by saving X_OAUTH2_ACCESS_TOKEN and "
            "X_OAUTH2_REFRESH_TOKEN in Admin, or regenerate the OAuth 1.0a access token and secret after setting the "
            "X app permissions to Read and write."
            f"{detail_suffix}"
        )
    if auth_mode == "oauth2_user" and status == 403:
        return (
            "X post failed with OAuth 2.0 user-context permissions. Regenerate the OAuth 2.0 tokens after enabling "
            "Read and write permissions and ensure the scopes include tweet.write, tweet.read, users.read, and offline.access."
            f"{detail_suffix}"
        )
    if status == 401:
        return f"X post failed with 401 Unauthorized. {UNAUTHORIZED_HELP}{detail_suffix}"
    if status == 429:
        return "X post failed because the X API rate limit was exceeded. Wait and retry from the approval queue."
    if status == 402:
        return PAYMENT_REQUIRED_HELP
    return f"X post failed. Check X credentials, write permissions, endpoint access, and rate limits.{detail_suffix}"


def _add_x_tweet(tweet: dict, source_type: str) -> dict:
    return add_intake_item({
        "channel": "x",
        "source_type": source_type,
        "source_id": tweet.get("id"),
        "author": tweet.get("author_id", ""),
        "text": tweet.get("text", ""),
        "received_at": tweet.get("created_at"),
        "conversation_id": tweet.get("conversation_id"),
    })

def create_x_draft(text: str, reply_to: str = None):
    risk_level, risks = check_claims(text)
    item = {
        "type": "x_reply" if reply_to else "x_post",
        "channel": "x",
        "draft": text,
        "reply_to": reply_to,
        "risk_level": risk_level,
        "risks": risks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    add_to_queue(item)
    log_action({"action": "x_draft", "risk": risk_level})
    log_event("x_draft_created", "info", "X draft created.", {"risk_level": risk_level, "reply": bool(reply_to)})
    return item


def prepare_x_payload(item_id: str) -> dict:
    item = get_approval_item(item_id)
    if not item:
        raise ValueError(f"Approval item not found: {item_id}")
    if item.get("channel") != "x" or item.get("type") not in {"x_post", "x_reply"}:
        raise ValueError("Approval item is not an X post or reply.")
    if item.get("status") != "approved":
        raise PermissionError("X payloads can only be prepared after approval.")
    if item.get("risk_level") == "block":
        raise PermissionError("Blocked X items cannot be prepared.")

    payload = {"text": item["draft"]}
    reply_to = item.get("reply_to") or item.get("external_source_id") or item.get("source", {}).get("source_id")
    if item.get("type") == "x_reply":
        if not reply_to:
            raise ValueError("X replies require a supplied mention/reply source id.")
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}

    result = {
        "method": "POST",
        "endpoint": "/2/tweets",
        "json": payload,
        "metadata": {"made_with_ai": True, "approval_item_id": item_id},
    }
    log_event("x_payload_prepared", "info", "X payload prepared after approval.", {"approval_item_id": item_id})
    return result


def post_approved_tweet(item_id: str, client_config: dict | None = None):
    payload = prepare_x_payload(item_id)
    if not feature_enabled("ENABLE_X_WRITE"):
        log_event(
            "x_post_skipped",
            "info",
            "X write is disabled; payload was not posted.",
            {"approval_item_id": item_id, "reason": "ENABLE_X_WRITE=false"},
        )
        log_action({
            "action": "x_post_blocked_by_feature_flag",
            "approval_item_id": item_id,
            "channel": "x",
            "final_action_status": "not_posted",
        })
        return {"sent": False, "reason": "ENABLE_X_WRITE=false", "payload": payload}

    if feature_enabled("REQUIRE_HUMAN_APPROVAL") and get_approval_item(item_id).get("status") != "approved":
        raise PermissionError("Human approval is required before posting to X.")

    auth_mode = "missing"
    try:
        load_env_file()
        config = client_config or {}
        http_post = config.get("http_post") or requests.post
        oauth2_access_token = config.get("oauth2_access_token") or get_env("X_OAUTH2_ACCESS_TOKEN")
        oauth2_error = None
        if oauth2_access_token or _has_oauth2_refresh_token(config):
            auth_mode = "oauth2_user"
            try:
                if not oauth2_access_token:
                    oauth2_access_token = refresh_oauth2_access_token(config)
                result_data = _post_tweet_with_oauth2(payload["json"], oauth2_access_token, http_post)
            except Exception as exc:
                oauth2_error = exc
                if _is_unauthorized(exc) and _has_oauth2_refresh_token(config):
                    try:
                        oauth2_access_token = refresh_oauth2_access_token(config)
                        result_data = _post_tweet_with_oauth2(payload["json"], oauth2_access_token, http_post)
                        oauth2_error = None
                    except Exception as refresh_exc:
                        oauth2_error = refresh_exc
                if oauth2_error and not _has_oauth1_user_credentials(config):
                    raise oauth2_error
                if oauth2_error:
                    log_event(
                        "x_post_oauth2_failed_oauth1_fallback",
                        "warning",
                        "OAuth 2.0 X post failed; falling back to OAuth 1.0a user credentials.",
                        {"approval_item_id": item_id, "http_status": _http_status(oauth2_error), "error": _x_post_failure_message(oauth2_error, auth_mode)},
                    )

        if not (oauth2_access_token or _has_oauth2_refresh_token(config)) or oauth2_error:
            auth_mode = "oauth1a_user"
            import tweepy

            consumer_key = config.get("consumer_key") or get_env("X_CONSUMER_KEY") or get_env("X_API_KEY")
            consumer_secret = config.get("consumer_secret") or get_env("X_CONSUMER_SECRET") or get_env("X_API_SECRET")
            client = tweepy.Client(
                bearer_token=config.get("bearer_token") or get_env("X_BEARER_TOKEN"),
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                access_token=config.get("access_token") or get_env("X_ACCESS_TOKEN"),
                access_token_secret=config.get("access_token_secret") or get_env("X_ACCESS_TOKEN_SECRET"),
                wait_on_rate_limit=True,
            )
            result = _create_tweet_with_retry(client, _tweet_kwargs_from_payload(payload["json"]))
            result_data = getattr(result, "data", result)
        mark_sent_or_posted(item_id)
        log_event("x_post_complete", "info", "Approved X item posted.", {"approval_item_id": item_id, "auth_mode": auth_mode})
        log_action({
            "action": "x_posted",
            "approval_item_id": item_id,
            "channel": "x",
            "auth_mode": auth_mode,
            "final_action_status": "sent_or_posted",
        })
        return {"sent": True, "result": result_data, "payload": payload, "auth_mode": auth_mode}
    except Exception as exc:
        message = _x_post_failure_message(exc, auth_mode)
        log_event(
            "x_post_failed",
            "error",
            "Approved X item failed to post.",
            {
                "approval_item_id": item_id,
                "auth_mode": auth_mode,
                "http_status": _http_status(exc),
                "error": message,
                "raw_error": str(exc),
            },
        )
        log_action({
            "action": "x_post_failed",
            "approval_item_id": item_id,
            "channel": "x",
            "auth_mode": auth_mode,
            "final_action_status": "failed",
            "error": message,
        })
        raise RuntimeError(message) from exc


def _tweet_kwargs_from_payload(payload_json: dict) -> dict:
    kwargs = {"text": payload_json.get("text", "")}
    reply = payload_json.get("reply") or {}
    if reply.get("in_reply_to_tweet_id"):
        kwargs["in_reply_to_tweet_id"] = reply["in_reply_to_tweet_id"]
    return kwargs
