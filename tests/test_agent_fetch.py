import httpx

from agent.fetch import fetch, parse_page

ARTICLE_HTML = """
<html><head>
<title>Attention Is Overrated</title>
<meta property="og:description" content="A contrarian take on attention.">
<script>var junk = 1;</script>
</head><body>
<nav>Home | About</nav>
<article><p>First real paragraph.</p><p>Second paragraph.</p></article>
</body></html>
"""


class TestParsePage:
    def test_extracts_title_description_and_text(self):
        page = parse_page(ARTICLE_HTML)
        assert page.title == "Attention Is Overrated"
        assert page.description == "A contrarian take on attention."
        assert "First real paragraph." in page.text
        assert "Second paragraph." in page.text
        assert "var junk" not in page.text

    def test_meta_name_description_fallback(self):
        html = '<html><head><meta name="description" content="plain meta"></head><body></body></html>'
        assert parse_page(html).description == "plain meta"

    def test_text_is_truncated(self):
        html = "<html><body><p>" + "word " * 5000 + "</p></body></html>"
        assert len(parse_page(html).text) <= 8000


class TestFetch:
    def test_returns_parsed_page_on_success(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, text=ARTICLE_HTML)
        )
        client = httpx.Client(transport=transport)
        result = fetch("https://example.com/a", client)
        assert result.error is None
        assert result.title == "Attention Is Overrated"

    def test_http_error_status_is_a_hard_error(self):
        transport = httpx.MockTransport(lambda req: httpx.Response(404))
        client = httpx.Client(transport=transport)
        result = fetch("https://example.com/gone", client)
        assert result.error == "HTTP 404"

    def test_network_failure_is_a_hard_error(self):
        def raise_error(req):
            raise httpx.ConnectError("boom")

        client = httpx.Client(transport=httpx.MockTransport(raise_error))
        result = fetch("https://example.com/x", client)
        assert result.error is not None
