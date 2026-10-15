"""Local Ollama Runtime Provider Adapter for TRACE Stage 5.

Connects to a local Ollama daemon (default: http://127.0.0.1:11434) using
the standard Ollama REST API. Implements configurable timeouts, controlled retries,
health probes, and explicit provider-unavailable failure handling.
"""

import time
import json
from typing import Optional, Dict, Any
import requests

from app.core.config import settings
from app.ml.stage5_llm.providers.base import LLMProvider, ProviderResult


class OllamaProvider(LLMProvider):
    """Adapter for local Ollama instruct models."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        import os
        self.base_url = (base_url or settings.TRACE_OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.TRACE_OLLAMA_MODEL
        env_timeout = os.getenv("TRACE_LLM_TIMEOUT_SEC")
        if timeout_sec is not None:
            self.timeout_sec = float(timeout_sec)
        elif env_timeout:
            try:
                self.timeout_sec = float(env_timeout)
            except ValueError:
                self.timeout_sec = settings.TRACE_LLM_TIMEOUT_SEC
        else:
            self.timeout_sec = settings.TRACE_LLM_TIMEOUT_SEC

        env_retries = os.getenv("TRACE_LLM_MAX_RETRIES")
        if max_retries is not None:
            self.max_retries = int(max_retries)
        elif env_retries:
            try:
                self.max_retries = int(env_retries)
            except ValueError:
                self.max_retries = settings.TRACE_LLM_MAX_RETRIES
        else:
            self.max_retries = settings.TRACE_LLM_MAX_RETRIES

    def is_available(self) -> bool:
        """Probe the Ollama daemon tags endpoint to check connectivity and model presence."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                full_models = [m.get("name", "") for m in data.get("models", [])]
                model_base = self.model_name.split(":")[0]
                # Check if model exists or is available
                return self.model_name in full_models or model_base in models
            return False
        except Exception:
            return False

    def get_provider_info(self) -> Dict[str, Any]:
        """Return runtime diagnostic details."""
        available = self.is_available()
        return {
            "provider": "ollama",
            "model": self.model_name,
            "base_url": self.base_url,
            "timeout_sec": self.timeout_sec,
            "max_retries": self.max_retries,
            "is_available": available,
            "setup_command": f"ollama run {self.model_name}"
        }

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> ProviderResult:
        """Call Ollama /api/generate with timeout and retry controls."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for deterministic, factual grounding
                "top_p": 0.9,
                "num_predict": 1500
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        endpoint = f"{self.base_url}/api/generate"
        guidance = (
            f"Ollama daemon could not be reached at {self.base_url}. "
            f"To enable Stage 5 synthesis, run: 'ollama run {self.model_name}' locally. "
            f"TRACE continues to function with Stages 1-4 intact."
        )

        attempts = 0
        last_error = None

        while attempts <= self.max_retries:
            attempts += 1
            t0 = time.perf_counter()
            try:
                resp = requests.post(
                    endpoint,
                    json=payload,
                    timeout=self.timeout_sec
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

                if resp.status_code == 200:
                    data = resp.json()
                    response_text = data.get("response", "").strip()

                    # Try parsing structured JSON
                    parsed_json = None
                    if json_mode:
                        try:
                            parsed_json = json.loads(response_text)
                        except json.JSONDecodeError:
                            # Model produced unformatted text despite format=json
                            pass

                    return ProviderResult(
                        text=response_text,
                        status="success",
                        provider_name="ollama",
                        model_name=self.model_name,
                        latency_ms=elapsed_ms,
                        timeout_sec=self.timeout_sec,
                        raw_json=parsed_json
                    )
                elif resp.status_code == 404:
                    return ProviderResult(
                        text="",
                        status="provider_unavailable",
                        provider_name="ollama",
                        model_name=self.model_name,
                        latency_ms=elapsed_ms,
                        timeout_sec=self.timeout_sec,
                        error_message=f"Model '{self.model_name}' not found on Ollama server (HTTP 404).",
                        setup_guidance=f"Pull model with: ollama pull {self.model_name}"
                    )
                else:
                    last_error = f"Ollama HTTP {resp.status_code}: {resp.text[:200]}"

            except requests.exceptions.Timeout:
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                return ProviderResult(
                    text="",
                    status="timeout",
                    provider_name="ollama",
                    model_name=self.model_name,
                    latency_ms=elapsed_ms,
                    timeout_sec=self.timeout_sec,
                    error_message=f"Ollama request timed out after {self.timeout_sec:.1f}s.",
                    setup_guidance=(
                        f"Ollama request exceeded configured timeout limit ({self.timeout_sec:.1f}s). "
                        "To increase timeout, set environment variable TRACE_LLM_TIMEOUT_SEC "
                        "(e.g. TRACE_LLM_TIMEOUT_SEC=120) or use a faster model."
                    )
                )
            except requests.exceptions.ConnectionError as e:
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                return ProviderResult(
                    text="",
                    status="provider_unavailable",
                    provider_name="ollama",
                    model_name=self.model_name,
                    latency_ms=elapsed_ms,
                    timeout_sec=self.timeout_sec,
                    error_message=f"Connection refused to {self.base_url}.",
                    setup_guidance=guidance
                )
            except Exception as e:
                last_error = str(e)
                time.sleep(0.5)

        return ProviderResult(
            text="",
            status="error",
            provider_name="ollama",
            model_name=self.model_name,
            latency_ms=0.0,
            timeout_sec=self.timeout_sec,
            error_message=f"Ollama failure after {attempts} attempts: {last_error}",
            setup_guidance=guidance
        )
