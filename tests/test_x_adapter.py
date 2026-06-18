import requests
import pytest

from msquared_agent.agent import generate_draft
from msquared_agent.approval_queue import approve_item
from msquared_agent.app_log import read_log_events
from msquared_agent.env_loader import read_env_values
from msquared_agent.settings import save_feature_flags
from msquared_agent.x_adapter import (
    build_oauth2_authorization_url,
    clear_oauth2_pending_flow,
    exchange_pending_oauth2_authorization_code,
    exchange_oauth2_authorization_code,
    fetch_x_feed,
    load_oauth2_pending_flow,
    post_approved_tweet,
    refresh_oauth2_access_token,
    save_oauth2_pending_flow,
    test_x_connection as run_x_connection_test,
)


class FakeResponse:
    def __init__(self, payload, status_code=200, url="https://api.x.com/test"):
        self.payload = payload
        self.status_code = status_code
        self.url = url

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error for {self.url}")
            error.response = self
            raise error


def test_x_monitor_handle_is_resolved_before_mentions_fetch():
    save_feature_flags({"ENABLE_X_READ": True})
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if "/users/by/username/" in url:
            return FakeResponse({"data": {"id": "2065865497237729280", "username": "MSQUARED_2026"}}, url=url)
        if "/mentions" in url:
            return FakeResponse(
                {"data": [{"id": "tweet_1", "author_id": "author_1", "text": "Question about DIIaC"}]},
                url=url,
            )
        raise AssertionError(f"Unexpected URL: {url}")

    items = fetch_x_feed({
        "oauth2_access_token": "test-token",
        "monitor_user_id": "@MSQUARED_2026",
        "query": "",
        "http_get": fake_get,
    })

    urls = [call["url"] for call in calls]
    assert "https://api.x.com/2/users/by/username/MSQUARED_2026" in urls
    assert "https://api.x.com/2/users/2065865497237729280/mentions" in urls
    assert "https://api.x.com/2/users/@MSQUARED_2026/mentions" not in urls
    assert len(items) == 1
    assert any(event["event"] == "x_user_resolved" for event in read_log_events())


def test_x_monitor_numeric_id_skips_handle_resolution():
    save_feature_flags({"ENABLE_X_READ": True})
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        assert "/users/by/username/" not in url
        return FakeResponse({"data": []}, url=url)

    fetch_x_feed({
        "oauth2_access_token": "test-token",
        "monitor_user_id": "2065865497237729280",
        "query": "",
        "http_get": fake_get,
    })

    assert calls == ["https://api.x.com/2/users/2065865497237729280/mentions"]


def test_x_feed_prefers_app_bearer_over_stale_oauth2_token():
    save_feature_flags({"ENABLE_X_READ": True})
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers})
        assert headers["Authorization"] == "Bearer app-bearer-token"
        return FakeResponse({"data": []}, url=url)

    fetch_x_feed({
        "bearer_token": "app-bearer-token",
        "oauth2_access_token": "stale-oauth2-token",
        "monitor_user_id": "2065865497237729280",
        "query": "",
        "http_get": fake_get,
    })

    assert calls == [{
        "url": "https://api.x.com/2/users/2065865497237729280/mentions",
        "headers": {"Authorization": "Bearer app-bearer-token"},
    }]


def test_x_feed_retries_transient_mention_failure():
    save_feature_flags({"ENABLE_X_READ": True})
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "/mentions" in url and calls.count(url) == 1:
            return FakeResponse({"title": "Temporary upstream error"}, status_code=500, url=url)
        if "/mentions" in url:
            return FakeResponse(
                {"data": [{"id": "tweet_1", "author_id": "author_1", "text": "Retry worked"}]},
                url=url,
            )
        raise AssertionError(f"Unexpected URL: {url}")

    items = fetch_x_feed({
        "oauth2_access_token": "test-token",
        "monitor_user_id": "2065865497237729280",
        "query": "",
        "http_get": fake_get,
    })

    assert len(items) == 1
    assert calls.count("https://api.x.com/2/users/2065865497237729280/mentions") == 2
    assert any(event["event"] == "x_api_retry" for event in read_log_events())


def test_x_unauthorized_logs_actionable_message():
    save_feature_flags({"ENABLE_X_READ": True})

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(
            {"title": "Unauthorized", "detail": "Token has expired."},
            status_code=401,
            url=url,
        )

    items = fetch_x_feed({
        "oauth2_access_token": "expired-token",
        "monitor_user_id": "2065865497237729280",
        "query": "",
        "http_get": fake_get,
    })

    events = read_log_events()
    failure = next(event for event in events if event["event"] == "x_fetch_failed")
    assert items == []
    assert failure["details"]["http_status"] == 401
    assert "user-context token" in failure["message"]
    assert "offline.access" in failure["message"]
    assert "Token has expired" in failure["message"]


def test_x_app_bearer_unauthorized_logs_bearer_guidance():
    save_feature_flags({"ENABLE_X_READ": True})

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(
            {"title": "Unauthorized", "detail": "Invalid bearer token."},
            status_code=401,
            url=url,
        )

    items = fetch_x_feed({
        "bearer_token": "invalid-app-bearer",
        "monitor_user_id": "2065865497237729280",
        "query": "",
        "http_get": fake_get,
    })

    events = read_log_events()
    failure = next(event for event in events if event["event"] == "x_fetch_failed")
    assert items == []
    assert failure["details"]["http_status"] == 401
    assert "app-only credential" in failure["message"]
    assert "OAuth 2.0 access token is a user-context token" not in failure["message"]
    assert "Invalid bearer" in failure["message"]


def test_x_search_payment_required_logs_partial_warning_after_mentions():
    save_feature_flags({"ENABLE_X_READ": True})

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/mentions" in url:
            return FakeResponse(
                {"data": [{"id": "tweet_1", "author_id": "author_1", "text": "Mention about DIIaC"}]},
                url=url,
            )
        if "/tweets/search/recent" in url:
            return FakeResponse({"title": "Payment Required"}, status_code=402, url=url)
        raise AssertionError(f"Unexpected URL: {url}")

    items = fetch_x_feed({
        "oauth2_access_token": "test-token",
        "monitor_user_id": "2065865497237729280",
        "query": "DIIaC OR MSquared",
        "http_get": fake_get,
    })

    events = read_log_events()
    assert len(items) == 1
    assert any(event["event"] == "x_fetch_source_failed" and event["details"]["http_status"] == 402 for event in events)
    assert any(event["event"] == "x_fetch_complete" for event in events)


def test_x_payment_required_logs_actionable_message():
    save_feature_flags({"ENABLE_X_READ": True})

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse({"title": "Payment Required"}, status_code=402, url=url)

    items = fetch_x_feed({
        "oauth2_access_token": "test-token",
        "monitor_user_id": "@MSQUARED_2026",
        "query": "",
        "http_get": fake_get,
    })

    events = read_log_events()
    assert items == []
    failure = next(event for event in events if event["event"] == "x_fetch_failed")
    assert failure["details"]["http_status"] == 402
    assert "Payment Required" in failure["message"]
    assert "numeric X user id" in failure["message"]


def test_oauth2_refresh_saves_rotated_tokens(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        captured["timeout"] = timeout
        return FakeResponse({
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 7200,
            "scope": "tweet.read users.read tweet.write offline.access",
        }, url=url)

    monkeypatch.setattr(requests, "post", fake_post)

    token = refresh_oauth2_access_token({
        "client_id": "client-id",
        "client_secret": "client-secret",
        "oauth2_refresh_token": "old-refresh-token",
    })

    values = read_env_values()
    assert token == "new-access-token"
    assert captured["url"] == "https://api.x.com/2/oauth2/token"
    assert captured["data"]["grant_type"] == "refresh_token"
    assert captured["data"]["refresh_token"] == "old-refresh-token"
    assert "Authorization" in captured["headers"]
    assert values["X_OAUTH2_ACCESS_TOKEN"] == "new-access-token"
    assert values["X_OAUTH2_REFRESH_TOKEN"] == "new-refresh-token"
    assert values["X_OAUTH2_ACCESS_TOKEN_EXPIRES_AT"]
    assert "new-access-token" not in str(read_log_events())


def test_oauth2_authorization_url_uses_pkce_and_requested_scopes():
    flow = build_oauth2_authorization_url({
        "client_id": "client-id",
        "callback_uri": "https://example.com/oauth/x/callback",
    })

    assert flow["authorization_url"].startswith("https://x.com/i/oauth2/authorize?")
    assert "client_id=client-id" in flow["authorization_url"]
    assert "code_challenge_method=S256" in flow["authorization_url"]
    assert "tweet.write" in flow["scope"]
    assert "offline.access" in flow["scope"]
    assert flow["code_verifier"]
    assert flow["state"]


def test_oauth2_authorization_code_exchange_saves_tokens():
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        captured["timeout"] = timeout
        return FakeResponse({
            "access_token": "new-user-access-token",
            "refresh_token": "new-user-refresh-token",
            "expires_in": 7200,
            "scope": "tweet.read tweet.write users.read offline.access",
        }, url=url)

    result = exchange_oauth2_authorization_code(
        "https://example.com/oauth/x/callback?state=state-123&code=auth-code-123",
        "verifier-123",
        "state-123",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "callback_uri": "https://example.com/oauth/x/callback",
        },
        http_post=fake_post,
    )

    values = read_env_values()
    assert result["ok"] is True
    assert captured["url"] == "https://api.x.com/2/oauth2/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "auth-code-123"
    assert captured["data"]["code_verifier"] == "verifier-123"
    assert "Authorization" in captured["headers"]
    assert values["X_OAUTH2_ACCESS_TOKEN"] == "new-user-access-token"
    assert values["X_OAUTH2_REFRESH_TOKEN"] == "new-user-refresh-token"
    assert "new-user-access-token" not in str(read_log_events())


def test_oauth2_pending_flow_can_resume_exchange():
    flow = {
        "authorization_url": "https://x.com/i/oauth2/authorize?response_type=code",
        "code_verifier": "verifier-123",
        "state": "state-123",
        "redirect_uri": "https://example.com/oauth/x/callback",
        "scope": "tweet.read tweet.write users.read offline.access",
    }
    save_oauth2_pending_flow(flow)
    assert load_oauth2_pending_flow()["state"] == "state-123"
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["data"] = data
        return FakeResponse({
            "access_token": "resumed-access-token",
            "refresh_token": "resumed-refresh-token",
            "expires_in": 7200,
            "scope": "tweet.read tweet.write users.read offline.access",
        }, url=url)

    result = exchange_pending_oauth2_authorization_code(
        "https://example.com/oauth/x/callback?state=state-123&code=auth-code-123",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
        http_post=fake_post,
    )

    values = read_env_values()
    assert result["ok"] is True
    assert captured["data"]["code"] == "auth-code-123"
    assert captured["data"]["code_verifier"] == "verifier-123"
    assert values["X_OAUTH2_ACCESS_TOKEN"] == "resumed-access-token"
    assert values["X_OAUTH2_REFRESH_TOKEN"] == "resumed-refresh-token"
    assert load_oauth2_pending_flow() == {}


def test_oauth2_pending_flow_can_be_cleared():
    save_oauth2_pending_flow({
        "authorization_url": "https://x.com/i/oauth2/authorize?response_type=code",
        "code_verifier": "verifier-123",
        "state": "state-123",
    })
    clear_oauth2_pending_flow()

    assert load_oauth2_pending_flow() == {}


def test_oauth2_exchange_rejects_authorization_start_url_with_clear_message():
    with pytest.raises(ValueError) as exc:
        exchange_oauth2_authorization_code(
            "https://x.com/i/oauth2/authorize?response_type=code&client_id=client-id",
            "verifier-123",
            "state-123",
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "callback_uri": "https://example.com/oauth/x/callback",
            },
        )

    message = str(exc.value)
    assert "authorization start URL" in message
    assert "final redirected URL" in message
    assert "code=" in message


def test_x_connection_uses_oauth2_users_me():
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse({"data": {"id": "2065274277448835072", "username": "MSQUARED_2026"}}, url=url)

    result = run_x_connection_test({
        "oauth2_access_token": "test-token",
        "http_get": fake_get,
    })

    assert result["ok"] is True
    assert result["auth_mode"] == "oauth2_user"
    assert result["checks"][0]["name"] == "authenticated_user"
    assert calls[0]["url"] == "https://api.x.com/2/users/me"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-token"


def test_x_connection_prefers_app_bearer_for_read_validation():
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers})
        assert headers["Authorization"] == "Bearer app-bearer-token"
        return FakeResponse({"data": {"id": "2065274277448835072", "username": "MSQUARED_2026"}}, url=url)

    result = run_x_connection_test({
        "bearer_token": "app-bearer-token",
        "oauth2_access_token": "stale-oauth2-token",
        "monitor_user_id": "2065274277448835072",
        "http_get": fake_get,
    })

    assert result["ok"] is True
    assert result["auth_mode"] == "app_bearer"
    assert calls[0]["url"] == "https://api.x.com/2/users/2065274277448835072"


def test_x_connection_reports_401_guidance():
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(
            {"title": "Unauthorized", "detail": "Invalid or expired token."},
            status_code=401,
            url=url,
        )

    result = run_x_connection_test({
        "oauth2_access_token": "expired-token",
        "http_get": fake_get,
    })

    assert result["ok"] is False
    assert result["http_status"] == 401
    assert "user-context token" in result["message"]
    assert "Invalid or expired token" in result["provider_detail"]


def test_post_approved_tweet_uses_oauth2_direct_request():
    save_feature_flags({"ENABLE_X_WRITE": True, "REQUIRE_HUMAN_APPROVAL": True})
    item = generate_draft("x_post", "Governed decisions need signed evidence.")
    approve_item(item["id"])
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse({"data": {"id": "tweet_123", "text": json["text"]}}, url=url)

    result = post_approved_tweet(item["id"], {
        "oauth2_access_token": "oauth2-user-token",
        "http_post": fake_post,
    })

    assert result["sent"] is True
    assert result["auth_mode"] == "oauth2_user"
    assert result["result"]["id"] == "tweet_123"
    assert calls == [
        {
            "url": "https://api.x.com/2/tweets",
            "headers": {"Authorization": "Bearer oauth2-user-token", "Content-Type": "application/json"},
            "json": {"text": item["draft"]},
            "timeout": 20,
        }
    ]


def test_post_approved_tweet_oauth1_permission_error_has_guidance(monkeypatch):
    import tweepy

    save_feature_flags({"ENABLE_X_WRITE": True, "REQUIRE_HUMAN_APPROVAL": True})
    item = generate_draft("x_post", "Governed decisions need human accountability.")
    approve_item(item["id"])

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def create_tweet(self, **kwargs):
            response = FakeResponse(
                {"detail": "Your client app is not configured with the appropriate oauth1 app permissions for this endpoint."},
                status_code=403,
                url="https://api.x.com/2/tweets",
            )
            response.raise_for_status()

    monkeypatch.setattr(tweepy, "Client", FakeClient)

    with pytest.raises(RuntimeError) as exc:
        post_approved_tweet(item["id"], {
            "consumer_key": "consumer-key",
            "consumer_secret": "consumer-secret",
            "access_token": "access-token",
            "access_token_secret": "access-token-secret",
            "allow_oauth1_fallback": True,
        })

    message = str(exc.value)
    assert "OAuth 1.0a app permissions" in message
    assert "X_OAUTH2_ACCESS_TOKEN" in message
    assert "Read and write" in message


def test_post_approved_tweet_falls_back_to_oauth1_when_oauth2_fails(monkeypatch):
    import tweepy

    save_feature_flags({"ENABLE_X_WRITE": True, "REQUIRE_HUMAN_APPROVAL": True})
    item = generate_draft("x_post", "Governed decisions need human accountability.")
    approve_item(item["id"])
    oauth2_calls = []
    oauth1_calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        oauth2_calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse({"title": "Unauthorized", "detail": "Expired token."}, status_code=401, url=url)

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def create_tweet(self, **kwargs):
            oauth1_calls.append(kwargs)
            return type("Result", (), {"data": {"id": "tweet_123", "text": kwargs["text"]}})()

    monkeypatch.setattr(tweepy, "Client", FakeClient)

    result = post_approved_tweet(item["id"], {
        "oauth2_access_token": "expired-oauth2-token",
        "consumer_key": "consumer-key",
        "consumer_secret": "consumer-secret",
        "access_token": "access-token",
        "access_token_secret": "access-token-secret",
        "allow_oauth1_fallback": True,
        "http_post": fake_post,
    })

    assert result["sent"] is True
    assert result["auth_mode"] == "oauth1a_user"
    assert oauth2_calls
    assert oauth1_calls == [{"text": item["draft"]}]
    assert any(event["event"] == "x_post_oauth2_failed_oauth1_fallback" for event in read_log_events())


def test_post_approved_tweet_blocks_oauth1_fallback_by_default(monkeypatch):
    import tweepy

    save_feature_flags({"ENABLE_X_WRITE": True, "REQUIRE_HUMAN_APPROVAL": True})
    item = generate_draft("x_post", "Governed decisions need human accountability.")
    approve_item(item["id"])

    class FakeClient:
        def __init__(self, **kwargs):
            raise AssertionError("OAuth 1.0a client should not be used unless fallback is explicitly allowed.")

    monkeypatch.setattr(tweepy, "Client", FakeClient)

    with pytest.raises(RuntimeError) as exc:
        post_approved_tweet(item["id"], {
            "consumer_key": "consumer-key",
            "consumer_secret": "consumer-secret",
            "access_token": "access-token",
            "access_token_secret": "access-token-secret",
        })

    message = str(exc.value)
    assert "OAuth 2.0 user-context tokens" in message
    assert "X_ALLOW_OAUTH1_POSTING_FALLBACK=true" in message
