"""Tests for per-platform backend model override on the API server."""
from unittest.mock import patch, MagicMock

_RUNTIME_KWARGS = {"api_key": "test-key", "base_url": None,
                   "provider": None, "api_mode": None,
                   "command": None, "args": []}


def _create_agent_with(extra: dict) -> MagicMock:
    from gateway.platforms.api_server import APIServerAdapter
    from gateway.config import PlatformConfig

    adapter = APIServerAdapter(PlatformConfig(extra=extra))

    with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
         patch("gateway.run._resolve_gateway_model") as mock_model, \
         patch("gateway.run._load_gateway_config") as mock_config, \
         patch("run_agent.AIAgent") as mock_agent_cls:
        mock_kwargs.return_value = dict(_RUNTIME_KWARGS)
        mock_model.return_value = "global/model"
        mock_config.return_value = {}
        mock_agent_cls.return_value = MagicMock()

        adapter._create_agent()

    return mock_agent_cls


@patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
def test_extra_model_overrides_global():
    """platforms.api_server.extra.model selects the backend model."""
    mock_agent_cls = _create_agent_with({"model": "openrouter/api-only-model"})
    assert mock_agent_cls.call_args.kwargs.get("model") == "openrouter/api-only-model"


@patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
def test_no_override_falls_back_to_global_model():
    """Without an override the API server uses the global config.yaml model."""
    mock_agent_cls = _create_agent_with({})
    assert mock_agent_cls.call_args.kwargs.get("model") == "global/model"


@patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
def test_env_var_sets_backend_model(monkeypatch):
    """API_SERVER_MODEL env var works when config extra is absent."""
    monkeypatch.setenv("API_SERVER_MODEL", "env/model")
    mock_agent_cls = _create_agent_with({})
    assert mock_agent_cls.call_args.kwargs.get("model") == "env/model"


@patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
def test_model_name_alone_does_not_change_backend_model():
    """model_name only changes the advertised /v1/models id, not the backend."""
    mock_agent_cls = _create_agent_with({"model_name": "my-agent"})
    assert mock_agent_cls.call_args.kwargs.get("model") == "global/model"
