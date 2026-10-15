"""LLM Provider Factory for TRACE Stage 5.

Provides unified instantiation of configured LLM backends:
- 'ollama': Local Ollama instruct runtime (default)
- 'mock': Deterministic test mock provider
"""

from typing import Optional
from app.core.config import settings
from app.ml.stage5_llm.providers.base import LLMProvider
from app.ml.stage5_llm.providers.ollama import OllamaProvider
from app.ml.stage5_llm.providers.mock import MockLLMProvider

_provider_instance: Optional[LLMProvider] = None


def get_llm_provider(
    provider_name: Optional[str] = None,
    force_new: bool = False,
    mock_mode: str = "normal",
    timeout_sec: Optional[float] = None
) -> LLMProvider:
    """Return an initialized LLMProvider instance.
    
    Args:
        provider_name: 'ollama' or 'mock'. Defaults to settings.TRACE_LLM_PROVIDER.
        force_new: If True, bypass singleton and instantiate new provider.
        mock_mode: Test mode when provider is 'mock' ('normal', 'unavailable', 'timeout', 'slow_success', etc.).
        timeout_sec: Optional explicit timeout in seconds.
    """
    import os
    global _provider_instance
    chosen_provider = (provider_name or settings.TRACE_LLM_PROVIDER or "ollama").strip().lower()

    if chosen_provider == "mock":
        return MockLLMProvider(simulate_mode=mock_mode, timeout_sec=timeout_sec)

    expected_timeout = timeout_sec if timeout_sec is not None else float(os.getenv("TRACE_LLM_TIMEOUT_SEC", str(settings.TRACE_LLM_TIMEOUT_SEC)))

    if _provider_instance is not None and not force_new:
        if getattr(_provider_instance, "timeout_sec", None) == expected_timeout:
            return _provider_instance

    if chosen_provider == "ollama":
        provider = OllamaProvider(timeout_sec=timeout_sec)
        _provider_instance = provider
        return provider
    else:
        # Fallback to Ollama
        provider = OllamaProvider(timeout_sec=timeout_sec)
        _provider_instance = provider
        return provider
