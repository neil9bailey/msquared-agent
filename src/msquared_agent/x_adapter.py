import os
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .app_log import log_event
from .approval_queue import add_to_queue
from .approval_queue import get_approval_item, mark_sent_or_posted
from .audit_store import log_action
from .claim_guard import check_claims
from .env_loader import get_env, load_env_file, save_env_values
from .intake_store import add_intake_item
from .settings import feature_enabled


X_API_BASE = "https://api.x.com"
PAYMENT_REQUIRED_HELP = (
    "X API returned 402 Payment Required. This usually means the current X API project plan "
    "does not include the requested endpoint. Use the numeric X user id to avoid handle lookup, "
    "and check that your plan includes user lookup, mentions, and recent search."
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
    query = config.get("query") if "query" in config else get_env("X_MONITOR_QUERY") or "DIIaC OR MSquared OR governed decision intelligence"
    monitor_user_id = config.get("monitor_user_id") if "monitor_user_id" in config else get_env("X_MONITOR_USER_ID")
    if not bearer_token:
        log_event(
            "x_fetch_skipped",
            "warning",
            "X API read is enabled but no OAuth 2.0 access token, refresh token, or app bearer token is configured.",
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
        import requests

        http_get = config.get("http_get") or requests.get
        mention_count, search_count, source_errors = _fetch_x_feed_with_token(
            items,
            bearer_token,
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
                import requests

                http_get = config.get("http_get") or requests.get
                mention_count, search_count, source_errors = _fetch_x_feed_with_token(
                    items,
                    refreshed_token,
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
            _x_failure_message(exc),
            {"error": str(exc), "http_status": _http_status(exc), "imported_count": len(items)},
        )
        log_action({
            "action": "x_feed_fetch_failed",
            "channel": "x",
            "final_action_status": "failed",
            "error": str(exc),
        })

    return items


def _fetch_x_feed_with_token(items, bearer_token, monitor_user_id, query, config, http_get) -> tuple[int, int, list[dict]]:
    headers = {"Authorization": f"Bearer {bearer_token}"}
    mention_count = 0
    search_count = 0
    source_errors = []
    if monitor_user_id:
        try:
            resolved_user_id = _resolve_x_user_id(monitor_user_id, headers, http_get)
            response = http_get(
                f"{X_API_BASE}/2/users/{resolved_user_id}/mentions",
                params={
                    "max_results": config.get("max_results", 10),
                    "tweet.fields": "author_id,created_at,conversation_id",
                },
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            for tweet in response.json().get("data", []):
                items.append(_add_x_tweet(tweet, "x_mention"))
                mention_count += 1
        except Exception as exc:
            source_errors.append({"source": "mentions", "exception": exc})

    if query:
        try:
            response = http_get(
                f"{X_API_BASE}/2/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": config.get("max_results", 10),
                    "tweet.fields": "author_id,created_at,conversation_id",
                },
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            for tweet in response.json().get("data", []):
                items.append(_add_x_tweet(tweet, "x_monitor"))
                search_count += 1
        except Exception as exc:
            source_errors.append({"source": "recent_search", "exception": exc})
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
            f"X {error['source']} source failed while other intake may still be available. {_x_failure_message(exc)}",
            {"source": error["source"], "http_status": _http_status(exc), "error": str(exc)},
        )


def _x_api_bearer_token(config: dict) -> str | None:
    return (
        config.get("oauth2_access_token")
        or get_env("X_OAUTH2_ACCESS_TOKEN")
        or config.get("bearer_token")
        or get_env("X_BEARER_TOKEN")
    )


def _has_oauth2_refresh_token(config: dict) -> bool:
    return bool(config.get("oauth2_refresh_token") or get_env("X_OAUTH2_REFRESH_TOKEN"))


def _is_unauthorized(exc: Exception) -> bool:
    return _http_status(exc) == 401 or "401" in str(exc)


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return int(status)
    text = str(exc)
    for candidate in (400, 401, 402, 403, 404, 429, 500, 502, 503):
        if str(candidate) in text:
            return candidate
    return None


def _x_failure_message(exc: Exception) -> str:
    if _http_status(exc) == 402:
        return PAYMENT_REQUIRED_HELP
    if _http_status(exc) == 401:
        return "X refresh failed with 401 Unauthorized. Check OAuth 2.0 token freshness, scopes, and app permissions."
    if _http_status(exc) == 403:
        return "X refresh failed with 403 Forbidden. Check X app permissions, OAuth scopes, and endpoint access."
    if _http_status(exc) == 429:
        return "X refresh failed because the X API rate limit was exceeded."
    return "X refresh failed. Check X credentials, permissions, rate limits, and monitor settings."


def refresh_oauth2_access_token(config: dict | None = None) -> str:
    config = config or {}
    refresh_token = config.get("oauth2_refresh_token") or get_env("X_OAUTH2_REFRESH_TOKEN")
    client_id = config.get("client_id") or get_env("X_CLIENT_ID")
    client_secret = config.get("client_secret") or get_env("X_CLIENT_SECRET")
    if not refresh_token:
        raise RuntimeError("X_OAUTH2_REFRESH_TOKEN is missing.")
    if not client_id:
        raise RuntimeError("X_CLIENT_ID is required to refresh OAuth 2.0 tokens.")

    import requests

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

    response = requests.post(
        "https://api.x.com/2/oauth2/token",
        headers=headers,
        data=data,
        timeout=20,
    )
    response.raise_for_status()
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

    response = http_get(
        f"{X_API_BASE}/2/users/by/username/{quote(username)}",
        params={"user.fields": "id,username"},
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
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
    reply_to = item.get("reply_to") or item.get("source", {}).get("source_id")
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

    try:
        import tweepy

        load_env_file()
        config = client_config or {}
        oauth2_access_token = config.get("oauth2_access_token") or get_env("X_OAUTH2_ACCESS_TOKEN")
        if oauth2_access_token or _has_oauth2_refresh_token(config):
            if not oauth2_access_token:
                oauth2_access_token = refresh_oauth2_access_token(config)
            client = tweepy.Client(bearer_token=oauth2_access_token, wait_on_rate_limit=True)
            try:
                result = client.create_tweet(user_auth=False, **_tweet_kwargs_from_payload(payload["json"]))
            except Exception as exc:
                if not _is_unauthorized(exc) or not _has_oauth2_refresh_token(config):
                    raise
                oauth2_access_token = refresh_oauth2_access_token(config)
                client = tweepy.Client(bearer_token=oauth2_access_token, wait_on_rate_limit=True)
                result = client.create_tweet(user_auth=False, **_tweet_kwargs_from_payload(payload["json"]))
        else:
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
            result = client.create_tweet(**_tweet_kwargs_from_payload(payload["json"]))
        mark_sent_or_posted(item_id)
        log_event("x_post_complete", "info", "Approved X item posted.", {"approval_item_id": item_id})
        log_action({
            "action": "x_posted",
            "approval_item_id": item_id,
            "channel": "x",
            "final_action_status": "sent_or_posted",
        })
        return {"sent": True, "result": result.data, "payload": payload}
    except Exception as exc:
        log_event(
            "x_post_failed",
            "error",
            "Approved X item failed to post.",
            {"approval_item_id": item_id, "error": str(exc)},
        )
        log_action({
            "action": "x_post_failed",
            "approval_item_id": item_id,
            "channel": "x",
            "final_action_status": "failed",
            "error": str(exc),
        })
        raise


def _tweet_kwargs_from_payload(payload_json: dict) -> dict:
    kwargs = {"text": payload_json.get("text", "")}
    reply = payload_json.get("reply") or {}
    if reply.get("in_reply_to_tweet_id"):
        kwargs["in_reply_to_tweet_id"] = reply["in_reply_to_tweet_id"]
    return kwargs
