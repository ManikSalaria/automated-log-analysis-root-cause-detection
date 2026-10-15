"""Deterministic Mock LLM Provider for Testing and Offline Environments.

Simulates structured LLM responses without external process dependencies.
Supports test modes: 'normal', 'unavailable', 'timeout', 'malformed_json',
and 'hallucinated_citation' to test validator resilience.
"""

import json
import re
from typing import Optional, Dict, Any
from app.ml.stage5_llm.providers.base import LLMProvider, ProviderResult


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for offline tests and validation."""

    def __init__(
        self,
        model_name: str = "mock-trace-instruct-v1",
        simulate_mode: str = "normal",
        timeout_sec: Optional[float] = None
    ):
        import os
        from app.core.config import settings
        self.model_name = model_name
        self.simulate_mode = simulate_mode
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

    def is_available(self) -> bool:
        return self.simulate_mode != "unavailable"

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model": self.model_name,
            "simulate_mode": self.simulate_mode,
            "timeout_sec": self.timeout_sec,
            "is_available": self.is_available()
        }

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> ProviderResult:
        """Generate deterministic structured response or simulated failure."""
        if self.simulate_mode == "unavailable":
            return ProviderResult(
                text="",
                status="provider_unavailable",
                provider_name="mock",
                model_name=self.model_name,
                latency_ms=1.2,
                timeout_sec=self.timeout_sec,
                error_message="Simulated: Mock LLM provider is configured as unavailable.",
                setup_guidance="Change simulate_mode to 'normal' or set TRACE_LLM_PROVIDER=ollama."
            )

        if self.simulate_mode == "timeout":
            return ProviderResult(
                text="",
                status="timeout",
                provider_name="mock",
                model_name=self.model_name,
                latency_ms=self.timeout_sec * 1000.0,
                timeout_sec=self.timeout_sec,
                error_message=f"Simulated: Mock LLM provider timed out after {self.timeout_sec:.1f}s.",
                setup_guidance=(
                    f"Mock generation exceeded timeout threshold ({self.timeout_sec:.1f}s). "
                    "To increase timeout, set environment variable TRACE_LLM_TIMEOUT_SEC."
                )
            )

        if self.simulate_mode == "malformed_json":
            return ProviderResult(
                text="This is raw unformatted text that violates the JSON contract.",
                status="success",
                provider_name="mock",
                model_name=self.model_name,
                latency_ms=10.0,
                raw_json=None
            )

        # Extract evidence IDs mentioned in prompt (e.g. E1, E2, E3...)
        evidence_ids = re.findall(r"\b(E\d+)\b", prompt)
        unique_ids = sorted(list(set(evidence_ids)))
        primary_id = unique_ids[0] if unique_ids else "E1"
        secondary_id = unique_ids[1] if len(unique_ids) > 1 else primary_id

        # Extract candidate diagnosis from prompt if available
        candidate_match = re.search(r"Candidate Diagnosis:\s*(.+)", prompt)
        candidate_diag = candidate_match.group(1).strip() if candidate_match else None

        # Extract historical incident codes from prompt if present
        hist_codes = re.findall(r"CODE:\s*(INC-[A-Za-z0-9_\-]+)", prompt)
        retrieved_codes = [c for c in hist_codes if not c.startswith("INC-QUERY") and not c.startswith("INC-CURRENT")]
        hist_code = retrieved_codes[0] if retrieved_codes else "INC-HISTORICAL"

        hist_cat_match = re.search(r"CATEGORY:\s*([A-Za-z0-9_]+)", prompt)
        hist_cat = hist_cat_match.group(1) if hist_cat_match else "CORROBORATED_CATEGORY"

        # Simulation Modes for Auditing Grounding Invariants
        rem1_action = "Ensure configuration keys and secrets are populated in target environment."
        rem1_rationale = "Prevents nil/null pointer or missing key assertions during initialization."
        rem2_supp = [secondary_id] if len(unique_ids) > 1 and self.simulate_mode in ("normal", "slow_success") else [primary_id]

        if self.simulate_mode == "hallucinated_citation":
            hyp1_text = "Root cause candidate indicated by primary log evidence."
            supporting = ["E99", "E88"]
            rem_supp = ["E99"]
            rem2_supp = ["E99"]
        elif self.simulate_mode == "irrelevant_evidence":
            hyp1_text = "Quantum entanglement decryptor failed due to cosmic ray bit flip on hardware chip."
            supporting = [primary_id]
            rem_supp = [primary_id]
        elif self.simulate_mode == "missing_citations":
            hyp1_text = candidate_diag or "Operational failure during service execution."
            supporting = []
            rem_supp = []
            rem2_supp = []
        elif self.simulate_mode == "try_catch_anti_pattern":
            hyp1_text = f"Null-pointer error in {primary_id} causing transaction rollback."
            supporting = [primary_id]
            rem_supp = [primary_id]
            rem1_action = "Add try-catch block around the transaction to catch NullPointerException and prevent rollbacks."
            rem1_rationale = "Catches the exception to suppress the error and avoid transaction rollback."
        elif self.simulate_mode == "missing_remediation_evidence":
            hyp1_text = f"{candidate_diag} verified in failure log evidence." if candidate_diag else f"Operational failure and service execution error in {primary_id}."
            supporting = [primary_id]
            rem_supp = []
            rem2_supp = []
        else:
            hyp1_text = f"{candidate_diag} verified in failure log evidence." if candidate_diag else f"Operational failure and service execution error in {primary_id}."
            supporting = [primary_id]
            rem_supp = [primary_id]

        # Extract secondary diagnosis from prompt if available
        sec_diag_match = re.search(r"\[" + re.escape(secondary_id) + r"\].*?CANDIDATE DIAGNOSIS:\s*([^\n]+)", prompt, re.DOTALL)
        sec_diag = sec_diag_match.group(1).strip() if sec_diag_match else None
        if not sec_diag or sec_diag == "None recorded":
            sec_diag = f"correlated failure condition in {hist_cat}"
        hyp2_text = f"Historical recurrence of {sec_diag} observed in {secondary_id}."

        mock_data = {
            "incident_summary": "Analysis of the incident indicates an operational failure during service execution.",
            "predicted_failure_category": "Identified by classifier pipeline as primary failure category.",
            "likely_root_causes": [
                {
                    "rank": 1,
                    "hypothesis": hyp1_text,
                    "supporting_evidence": supporting,
                    "conflicting_evidence": [],
                    "confidence_assessment": f"High qualitative confidence based on signature match in {primary_id}."
                },
                {
                    "rank": 2,
                    "hypothesis": hyp2_text,
                    "supporting_evidence": [secondary_id] if len(unique_ids) > 1 and self.simulate_mode in ("normal", "slow_success") else [primary_id],
                    "conflicting_evidence": [],
                    "confidence_assessment": "Moderate qualitative confidence; historical precedent."
                }
            ],
            "recommended_investigations": [
                {
                    "step_number": 1,
                    "target_hypothesis": "Verify configuration parameter and resource accessibility.",
                    "action": f"Inspect log lines referenced in {primary_id} and query upstream connection status.",
                    "expected_outcome": "Confirmation whether the resource was unreachable or configuration is missing."
                },
                {
                    "step_number": 2,
                    "target_hypothesis": "Check service metrics and queue latencies.",
                    "action": "Review host telemetry around the failure timestamp.",
                    "expected_outcome": "Identification of resource spikes or network drops."
                }
            ],
            "remediation_suggestions": [
                {
                    "rank": 1,
                    "action": rem1_action,
                    "rationale": rem1_rationale,
                    "prerequisites": ["Access to deployment environment configuration vault."],
                    "validation_steps": ["Run qualification dry-run test suite to confirm passing assertion."],
                    "is_advisory_only": True,
                    "supporting_evidence": rem_supp
                },
                {
                    "rank": 2,
                    "action": "Implement exponential backoff retry for network dependency calls.",
                    "rationale": "Mitigates transient 503 Service Unavailable or gateway timeout failures.",
                    "prerequisites": ["Idempotency support on target downstream endpoint."],
                    "validation_steps": ["Trigger simulated connection drop and observe successful retry."],
                    "is_advisory_only": True,
                    "supporting_evidence": rem2_supp
                }
            ],
            "uncertainties": [
                "Underlying root cause is inferred based on available log lines; no full heap dump is attached.",
                "Remediation outcome cannot be guaranteed without executing qualification pipeline."
            ],
            "historical_cases": [
                {
                    "incident_code": hist_code,
                    "evidence_id": secondary_id,
                    "failure_category": hist_cat,
                    "similarity_score": 0.88,
                    "relevance_notes": "Similar stack trace signature observed in historical run."
                }
            ] if retrieved_codes else [],
            "human_review_required": True
        }

        latency = 27600.0 if self.simulate_mode == "slow_success" else 12.5
        return ProviderResult(
            text=json.dumps(mock_data),
            status="success",
            provider_name="mock",
            model_name=self.model_name,
            latency_ms=latency,
            timeout_sec=self.timeout_sec,
            raw_json=mock_data
        )
