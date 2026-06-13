from msquared_agent.app_log import read_log_events
from msquared_agent.env_loader import read_env_values
from msquared_agent.settings import save_feature_flags
from msquared_agent.x_adapter import fetch_x_feed, refresh_oauth2_access_token


class FakeResponse:
    def __init__(self, payload, status_code=200, url="https://api.x.com/test"):
        self.payload = payload
        self.status_code = status_code
        self.url = url

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error for {self.url}")


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
    import requests

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
