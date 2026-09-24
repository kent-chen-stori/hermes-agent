"""Behavioral coverage for GPT-6 tier backport across the active routes."""

from decimal import Decimal
from types import SimpleNamespace

import agent.model_metadata as mm
from agent.codex_catalog import fetch_codex_catalog_entries
from agent.auxiliary_client import _compression_threshold_for_model
from agent.transports.chat_completions import _reasoning_config_for_model
from agent.usage_pricing import CanonicalUsage, _OFFICIAL_DOCS_PRICING, estimate_usage_cost, resolve_billing_route
from hermes_cli.codex_models import _add_forward_compat_models, _fetch_models_from_api
from hermes_cli.model_switch import _model_sort_key
from hermes_cli.models import OPENROUTER_MODELS, _PROVIDER_MODELS


def test_catalog_routes_and_alias_sort():
    for tier in ("sol", "terra", "luna"):
        slug = f"gpt-6-{tier}"
        assert f"openai/{slug}" in dict(OPENROUTER_MODELS)
        assert f"openai/{slug}" in _PROVIDER_MODELS["nous"]
        assert slug in _PROVIDER_MODELS["openai-api"]
        assert slug in _PROVIDER_MODELS["openai-codex"]
        assert f"openai/{slug}-pro" in _PROVIDER_MODELS["nous"]
        assert f"{slug}-pro" in _PROVIDER_MODELS["openai-api"]
        assert _add_forward_compat_models(["gpt-5.5"]).count(slug) == 1
        assert mm._CODEX_OAUTH_CONTEXT_FALLBACK[slug] < mm.DEFAULT_CONTEXT_LENGTHS[slug]
        assert _compression_threshold_for_model(slug, "openai-codex") == 0.85
        assert _compression_threshold_for_model(slug, "openrouter") is None
        assert _reasoning_config_for_model(slug, {"effort": "ultra"})["effort"] == "max"
    ordered = ["gpt-6-luna", "gpt-6-terra", "gpt-6-sol", "gpt-5.6-sol"]
    ordered.sort(key=lambda m: _model_sort_key(m, "gpt"))
    assert ordered[0] == "gpt-6-sol"


def test_codex_does_not_invent_public_api_pro_variants(tmp_path):
    import json
    from hermes_cli.codex_models import DEFAULT_CODEX_MODELS, _read_cache_models

    assert not any(mid.endswith("-pro") for mid in DEFAULT_CODEX_MODELS)
    assert not any(mid.endswith("-pro") for mid in _add_forward_compat_models(["gpt-5.5"]))
    (tmp_path / "models_cache.json").write_text(json.dumps({"models": [
        {"slug": "gpt-5.6-sol-pro"}, {"slug": "gpt-5.6-sol"},
    ]}))
    assert _read_cache_models(tmp_path) == ["gpt-5.6-sol"]


def test_catalog_fetch_newest_and_compat_fallback(monkeypatch):
    urls = []

    def get(url):
        urls.append(url)
        entries = [] if url.endswith("99.0.0") else [{"slug": "gpt-5.5", "context_window": 272000}]
        return SimpleNamespace(status_code=200, json=lambda: {"models": entries})

    assert fetch_codex_catalog_entries(get)[0]["slug"] == "gpt-5.5"
    assert urls[0].endswith("99.0.0") and urls[1].endswith("0.0.0")
    urls.clear()
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, **kw: get(url))
    assert "gpt-5.5" in _fetch_models_from_api("tok")
    monkeypatch.setattr(mm.requests, "get", lambda url, **kw: get(url))
    monkeypatch.setattr(mm, "_codex_oauth_context_cache", {})
    assert mm._fetch_codex_oauth_context_lengths("tok")["gpt-5.5"] == 272000


def test_catalog_recovers_from_first_request_error():
    urls = []

    def get(url):
        urls.append(url)
        if url.endswith("99.0.0"):
            raise OSError("temporary network failure")
        return SimpleNamespace(status_code=200, json=lambda: {"models": [{"slug": "gpt-6-sol"}]})

    assert fetch_codex_catalog_entries(get) == [{"slug": "gpt-6-sol"}]
    assert len(urls) == 2


def test_newest_catalog_does_not_fall_back_when_nonempty():
    urls = []

    def get(url):
        urls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"models": [{"slug": "gpt-6-sol"}]})

    assert fetch_codex_catalog_entries(get) == [{"slug": "gpt-6-sol"}]
    assert len(urls) == 1


def test_codex_responses_wire_effort_for_new_tier():
    from agent.transports import get_transport
    import agent.transports.codex  # noqa: F401 — register transport

    transport = get_transport("codex_responses")
    for slug in ("gpt-6-sol", "gpt-6-terra", "gpt-6-luna"):
        kwargs = transport.build_kwargs(
            model=slug, messages=[{"role": "user", "content": "hi"}], tools=[],
            reasoning_config={"enabled": True, "effort": "ultra"},
        )
        assert kwargs["model"] == slug
        assert kwargs["reasoning"]["effort"] == "max"


def test_published_pricing_and_unpublished_terra():
    for slug in ("gpt-6-sol", "gpt-6-luna"):
        assert resolve_billing_route(slug, provider="openai-api").provider == "openai"
        entry = _OFFICIAL_DOCS_PRICING[("openai", slug)]
        assert _OFFICIAL_DOCS_PRICING[("openai", slug + "-pro")] is entry
        assert entry.cache_read_cost_per_million == entry.input_cost_per_million * Decimal("0.1")
        assert entry.cache_write_cost_per_million == entry.input_cost_per_million * Decimal("1.25")
    assert ("openai", "gpt-6-terra") not in _OFFICIAL_DOCS_PRICING
    below = estimate_usage_cost("gpt-6-sol", CanonicalUsage(input_tokens=272_000, output_tokens=1000), provider="openai-api")
    above = estimate_usage_cost("gpt-6-sol", CanonicalUsage(input_tokens=272_001, output_tokens=1000), provider="openai-api")
    assert below.amount_usd == Decimal("0.554")
    assert above.amount_usd == Decimal("1.103004")
