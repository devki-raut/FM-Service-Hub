from app.teams import _teams_asset_url


class DummyUrl:
    scheme = "http"
    netloc = "internal:8609"


class DummyRequest:
    url = DummyUrl()

    def __init__(self, headers=None):
        self.headers = headers or {}


class DummySettings:
    def __init__(self, public_base_url=""):
        self.public_base_url = public_base_url


def test_teams_asset_url_uses_configured_public_base_url():
    request = DummyRequest()
    settings = DummySettings("https://example.com/fmservicehub-poc/")

    url = _teams_asset_url(request, settings, "/assets/visuals/page%201.png")

    assert url == "https://example.com/fmservicehub-poc/assets/visuals/page%201.png"


def test_teams_asset_url_uses_forwarded_proxy_headers_when_no_public_base_url():
    request = DummyRequest(
        {
            "x-forwarded-proto": "https",
            "x-forwarded-host": "example.com",
            "x-forwarded-prefix": "/fmservicehub-poc",
        }
    )
    settings = DummySettings()

    url = _teams_asset_url(request, settings, "assets/visuals/page.png")

    assert url == "https://example.com/fmservicehub-poc/assets/visuals/page.png"