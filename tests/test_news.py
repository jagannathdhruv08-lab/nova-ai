import news


def test_parse_date_input_supports_common_formats():
    assert news.parse_date_input("16-july-2026") == "2026-07-16"
    assert news.parse_date_input("16 july 2026") == "2026-07-16"
    assert news.parse_date_input("today") is None


def test_get_news_for_request_handles_topic_queries(monkeypatch):
    captured = {}

    def fake_fetch(url, params):
        captured["url"] = url
        captured["params"] = params
        return [{"title": "MS Dhoni announces comeback", "source": {"name": "ESPN"}}], None

    monkeypatch.setattr(news, "_fetch", fake_fetch)

    result = news.get_news_for_request("tell me current news about m.s dhoni")

    assert "MS Dhoni announces comeback" in result
    assert captured["params"]["q"] == "m.s dhoni"
    assert captured["params"]["pageSize"] == 10


def test_get_news_for_request_handles_main_news(monkeypatch):
    captured = {}

    def fake_fetch(url, params):
        captured["url"] = url
        captured["params"] = params
        return [{"title": "Main headline"}, {"title": "Second headline"}], None

    monkeypatch.setattr(news, "_fetch", fake_fetch)

    result = news.get_news_for_request("main news for 16 july 2026")

    assert "Main headline" in result
    # Dated main-news MUST use the /everything endpoint: top-headlines
    # ignores from/to params, which would mislabel articles under a
    # wrong date heading.
    assert captured["url"] == news.EVERYTHING_URL
    assert captured["params"]["from"] == "2026-07-16"
    assert captured["params"]["to"] == "2026-07-16"
