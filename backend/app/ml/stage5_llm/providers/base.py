"""Abstract Base Class for LLM Runtime Providers.

Defines the contract for LLM inference backends (Ollama, Mock, and future cloud adapters).
Enforces timeouts, error encapsulation, and provider diagnostic health checks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ProviderResult:
    """Standardized output from an LLM provider generation call."""
    text: str
    status: str  # "success", "provider_unavailable", "timeout", "error"
    provider_name: str
    model_name: str
    latency_ms: float = 0.0
    timeout_sec: Optional[float] = None
    raw_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    setup_guidance: Optional[str] = None


class LLMProvider(ABC):
    """Abstract interface for LLM backends."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> ProviderResult:
        """Execute text generation with the configured LLM.
        
        Args:
            prompt: User message containing sanitized evidence.
            system_prompt: System prompt with role, instructions, and injection guards.
            json_mode: If True, request structured JSON output from the model.
        
        Returns:
            ProviderResult containing raw text or parsed JSON, latency, and status.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the LLM provider daemon and configured model are reachable."""
        pass

    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """Return diagnostic metadata about the provider runtime and model."""
        pass
