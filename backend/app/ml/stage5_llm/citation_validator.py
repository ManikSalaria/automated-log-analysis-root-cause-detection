"""Citation and Evidence Grounding Validator for TRACE Stage 5.

Enforces strict grounding invariants:
1. Invalid or hallucinated evidence IDs (e.g. E99) are never silently substituted with fallback citations.
2. Claims with missing or invalid citations are explicitly marked unsupported or omitted from grounded findings.
3. Citation source metadata and incident references must strictly match the supplied evidence package.
4. Distinguishes syntactically valid citation IDs from evidence that genuinely supports a claim via diagnostic keyword and lexical relevance analysis.
5. Surfaces transparent disclosures regarding semantic verification limitations (uncalibrated heuristic proxy, not formal NLI entailment).
6. Remediation suggestions must be grounded in valid evidence and remain strictly advisory.
"""

import re
from typing import Dict, Any, List, Tuple, Set, Optional
from app.schemas.synthesis_schema import (
    SynthesisReport, RootCauseHypothesis, EvidenceItem,
    InvestigationStep, RemediationSuggestion, HistoricalCaseReference
)

# Common English and domain-neutral stop words
_STOP_WORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "to", "was", "were",
    "will", "with", "this", "these", "those", "then", "there", "their", "they",
    "have", "had", "can", "could", "should", "would", "may", "might", "must",
    "about", "into", "over", "after", "before", "between", "under", "above",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "s", "t", "just", "don", "should", "now", "here", "what", "which", "who"
}

DISCLOSURE_ENTAILMENT_LIMITATION = (
    "Semantic Verification Limitations: Claim-to-evidence verification relies on heuristic "
    "token overlap and diagnostic keyword consistency checks. It does NOT constitute formal "
    "natural language inference (NLI) entailment or mathematical proof. Syntactically valid "
    "and keyword-aligned evidence still requires human engineering review."
)


def extract_significant_tokens(text: str) -> Set[str]:
    """Extract normalized alphanumeric tokens from text, filtering out stop words.
    
    Splits compound terms (e.g. 'storage_cluster_id', 'test_vme') into individual
    informative tokens as well as retaining the composite if meaningful.
    """
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z0-9_\-\.]{3,}", text.lower())
    tokens = set()
    for w in words:
        sub_tokens = re.split(r"[\._\-]", w)
        for st in sub_tokens:
            if len(st) >= 3 and st not in _STOP_WORDS:
                tokens.add(st)
        if len(w) >= 3 and w not in _STOP_WORDS:
            tokens.add(w)
    return tokens


def evaluate_evidence_relevance(
    claim_text: str,
    evidence_snippet: str
) -> Tuple[float, List[str], str]:
    """Evaluate whether an evidence snippet genuinely supports a claim.
    
    Distinguishes syntactically valid evidence citations from evidence that
    genuinely contains overlapping diagnostic keywords or failure signatures.
    
    Returns:
        Tuple of (relevance_ratio, overlapping_keywords, support_assessment)
        where support_assessment in ('SUPPORTED', 'WEAK_SUPPORT', 'IRRELEVANT_EVIDENCE')
    """
    claim_tokens = extract_significant_tokens(claim_text)
    evidence_tokens = extract_significant_tokens(evidence_snippet)

    if not claim_tokens:
        return 0.5, [], "SUPPORTED"

    overlap = claim_tokens.intersection(evidence_tokens)
    overlap_list = sorted(list(overlap))

    # Overlap ratio relative to claim size
    ratio = len(overlap) / max(1, min(len(claim_tokens), 8))

    if len(overlap) >= 2 or ratio >= 0.25:
        assessment = "SUPPORTED"
    elif len(overlap) == 1:
        assessment = "WEAK_SUPPORT"
    else:
        assessment = "IRRELEVANT_EVIDENCE"

    return ratio, overlap_list, assessment


def sanitize_confidence_assessment(conf_raw: Any, classifier_prediction: Dict[str, Any]) -> str:
    """Ensure LLM-generated confidence assessments are not presented as calibrated probabilities.
    
    Unless backed by an actual calibrated model output (e.g. from an ML classifier),
    any percentage (e.g. '95%') or probability claim (e.g. '0.90 probability') is explicitly
    annotated as an uncalibrated qualitative heuristic.
    """
    conf_str = str(conf_raw or "Inferred qualitative hypothesis.").strip()
    if not conf_str:
        return "Qualitative confidence assessment: Inferred qualitative hypothesis."

    clf_conf = classifier_prediction.get("confidence")
    clf_model = classifier_prediction.get("model_name", "ML Classifier")

    has_percent = bool(re.search(r"\b\d+(\.\d+)?%", conf_str))
    has_prob = bool(re.search(r"\b(probability|calibrated|statistical)\b", conf_str, re.I))
    has_decimal = bool(re.search(r"\b0\.\d{2,}\b", conf_str))

    if has_percent or has_prob or has_decimal:
        if clf_conf is not None and isinstance(clf_conf, (int, float)) and clf_conf > 0.0:
            calibrated_pct = f"{clf_conf * 100:.1f}%"
            conf_str = (
                f"Qualitative confidence assessment: {conf_str} "
                f"[Calibrated ML Reference: {clf_model} estimated {calibrated_pct} feature confidence; "
                "LLM narrative confidence is an uncalibrated qualitative assessment]"
            )
        else:
            conf_str = (
                f"Qualitative confidence assessment (uncalibrated heuristic): {conf_str} "
                "[Note: Not a statistically calibrated probability; LLM confidence is qualitative only]"
            )
    return conf_str


def validate_and_sanitize_synthesis(
    raw_data: Dict[str, Any],
    evidence_items: List[EvidenceItem],
    classifier_prediction: Dict[str, Any],
    allow_limited_evidence: bool = True
) -> Tuple[SynthesisReport, Dict[str, Any]]:
    """Validate and sanitize an LLM-generated synthesis report against supplied evidence.
    
    Enforces that:
    1. Invalid or hallucinated evidence IDs are stripped and NEVER substituted with E1 or other citations.
    2. Missing or invalid citations mark hypotheses as unsupported with explicit validation warnings.
    3. Syntactically valid citations are vetted for topical/diagnostic relevance against the claim.
    4. Historical incident codes and metadata must match canonical records in the evidence package.
    5. Remediation suggestions citing invalid IDs are flagged as ungrounded and remain advisory.
    
    Returns:
        Tuple of (SynthesisReport, validation_details)
    """
    valid_ids: Set[str] = {item.evidence_id for item in evidence_items}
    evidence_id_map: Dict[str, EvidenceItem] = {item.evidence_id: item for item in evidence_items}
    valid_codes_map: Dict[str, EvidenceItem] = {
        item.incident_code: item for item in evidence_items if item.incident_code
    }

    hallucinated_citations: List[str] = []
    unverified_incident_codes: List[str] = []
    metadata_mismatches: List[str] = []
    unsupported_claims: List[Dict[str, Any]] = []
    global_validation_warnings: List[str] = []

    total_citations_checked = 0
    syntactically_valid_citations_count = 0
    evidentially_supported_citations_count = 0
    valid_citations_count = 0

    # 1. Validate Root Cause Hypotheses
    raw_hypotheses = raw_data.get("likely_root_causes", [])
    sanitized_hypotheses: List[RootCauseHypothesis] = []

    for idx, h in enumerate(raw_hypotheses, start=1):
        h_text = str(h.get("hypothesis", "Inferred failure candidate based on log signature.")).strip()
        raw_supp = h.get("supporting_evidence", [])
        raw_conf = h.get("conflicting_evidence", [])
        h_warnings: List[str] = []

        clean_supp: List[str] = []
        irrelevant_supp: List[str] = []
        hypothesis_hallucinations: List[str] = []

        if not raw_supp:
            # Missing citations entirely
            warn = (
                f"Hypothesis rank {idx} ('{h_text[:60]}...') provided no supporting evidence citations. "
                "Flagged as unsupported."
            )
            h_warnings.append(warn)
            global_validation_warnings.append(warn)
            unsupported_claims.append({
                "type": "HYPOTHESIS",
                "rank": idx,
                "hypothesis": h_text,
                "grounding_status": "UNSUPPORTED_MISSING_CITATION",
                "reason": "No evidence citations provided."
            })
            is_grounded = False
            grounding_status = "UNSUPPORTED_MISSING_CITATION"
        else:
            for cite in raw_supp:
                total_citations_checked += 1
                cite_str = str(cite).strip().upper()
                if cite_str in valid_ids:
                    syntactically_valid_citations_count += 1
                    # Check semantic / lexical support
                    evidence_item = evidence_id_map[cite_str]
                    ratio, overlap_words, assessment = evaluate_evidence_relevance(h_text, evidence_item.snippet)
                    if assessment == "IRRELEVANT_EVIDENCE":
                        irrel_warn = (
                            f"Hypothesis rank {idx} cited valid evidence ID '{cite_str}', but the evidence "
                            "snippet contains zero topical or diagnostic overlap with the claim. "
                            f"Evidence ID '{cite_str}' does not genuinely support this hypothesis."
                        )
                        h_warnings.append(irrel_warn)
                        global_validation_warnings.append(irrel_warn)
                        irrelevant_supp.append(cite_str)
                    else:
                        clean_supp.append(cite_str)
                        evidentially_supported_citations_count += 1
                        valid_citations_count += 1
                else:
                    hallucinated_citations.append(cite_str)
                    hypothesis_hallucinations.append(cite_str)
                    hall_warn = (
                        f"Hypothesis rank {idx} cited invalid evidence ID '{cite_str}'. "
                        "Invalid evidence IDs are never substituted with fallback citations."
                    )
                    h_warnings.append(hall_warn)
                    global_validation_warnings.append(hall_warn)

            # Determine hypothesis grounding status
            # CRITICAL INVARIANT: DO NOT FALLBACK TO E1 IF clean_supp IS EMPTY!
            if not clean_supp:
                is_grounded = False
                if hypothesis_hallucinations and not irrelevant_supp:
                    grounding_status = "UNSUPPORTED_INVALID_CITATION"
                    reason = f"All cited evidence IDs {hypothesis_hallucinations} are invalid/hallucinated."
                elif irrelevant_supp and not hypothesis_hallucinations:
                    grounding_status = "UNSUPPORTED_IRRELEVANT_EVIDENCE"
                    reason = f"Cited evidence IDs {irrelevant_supp} contain no diagnostic support for claim."
                else:
                    grounding_status = "UNSUPPORTED_INVALID_CITATION"
                    reason = "No valid, relevant supporting evidence citations found."

                unsupported_claims.append({
                    "type": "HYPOTHESIS",
                    "rank": idx,
                    "hypothesis": h_text,
                    "grounding_status": grounding_status,
                    "reason": reason
                })
            elif len(clean_supp) < len(raw_supp):
                is_grounded = True
                grounding_status = "PARTIALLY_SUPPORTED"
                part_warn = (
                    f"Hypothesis rank {idx} contains dropped or unverified citations. "
                    f"Partially supported by verified citations: {clean_supp}."
                )
                h_warnings.append(part_warn)
            else:
                is_grounded = True
                grounding_status = "SUPPORTED"

        # Validate conflicting evidence
        clean_conf: List[str] = []
        for cite in raw_conf:
            total_citations_checked += 1
            cite_str = str(cite).strip().upper()
            if cite_str in valid_ids:
                clean_conf.append(cite_str)
                valid_citations_count += 1
                syntactically_valid_citations_count += 1
                conf_note = f"Hypothesis rank {idx} is contested by conflicting evidence citation [{cite_str}]."
                h_warnings.append(conf_note)
            else:
                hallucinated_citations.append(cite_str)
                conf_hall_warn = (
                    f"Hypothesis rank {idx} cited invalid conflicting evidence ID '{cite_str}' (omitted)."
                )
                h_warnings.append(conf_hall_warn)
                global_validation_warnings.append(conf_hall_warn)

        conf_str = sanitize_confidence_assessment(h.get("confidence_assessment"), classifier_prediction)

        sanitized_hypotheses.append(RootCauseHypothesis(
            rank=h.get("rank", idx),
            hypothesis=h_text,
            supporting_evidence=clean_supp,
            conflicting_evidence=clean_conf,
            confidence_assessment=conf_str,
            is_grounded=is_grounded,
            grounding_status=grounding_status,
            validation_warnings=h_warnings
        ))

    # 2. Validate Historical Cases References (Match Metadata Strictly)
    raw_cases = raw_data.get("historical_cases", [])
    sanitized_cases: List[HistoricalCaseReference] = []

    for c in raw_cases:
        code = str(c.get("incident_code", "")).strip()
        e_id = str(c.get("evidence_id", "")).strip().upper()
        cat = str(c.get("failure_category", "")).strip()
        case_warnings: List[str] = []
        meta_verified = True

        if code:
            if code in valid_codes_map:
                matched_item = valid_codes_map[code]

                # Check evidence ID correspondence
                canonical_e_id = matched_item.evidence_id
                if e_id and e_id != canonical_e_id:
                    mismatch_warn = (
                        f"Historical case '{code}' was cited with evidence ID '{e_id}', "
                        f"but actual evidence package assigns '{code}' to '{canonical_e_id}'. "
                        "Reconciled to ground-truth evidence ID."
                    )
                    case_warnings.append(mismatch_warn)
                    metadata_mismatches.append(mismatch_warn)
                    global_validation_warnings.append(mismatch_warn)
                    meta_verified = False

                # Check failure category correspondence
                canonical_cat = matched_item.failure_category or "CORROBORATED"
                if cat and matched_item.failure_category and cat.upper() != matched_item.failure_category.upper():
                    cat_mismatch = (
                        f"Historical case '{code}' reported category '{cat}', "
                        f"but verified ground truth is '{canonical_cat}'. Reconciled to verified category."
                    )
                    case_warnings.append(cat_mismatch)
                    metadata_mismatches.append(cat_mismatch)
                    global_validation_warnings.append(cat_mismatch)
                    meta_verified = False

                sanitized_cases.append(HistoricalCaseReference(
                    incident_code=code,
                    evidence_id=canonical_e_id,
                    failure_category=canonical_cat,
                    similarity_score=float(matched_item.retrieval_score or c.get("similarity_score", 0.0)),
                    relevance_notes=str(c.get("relevance_notes", "Corroborated historical incident.")),
                    metadata_verified=meta_verified,
                    validation_warnings=case_warnings
                ))
            else:
                unverified_incident_codes.append(code)
                code_warn = (
                    f"Historical case reference '{code}' is not present in the retrieved knowledge base. "
                    "Omitted from verified historical cases."
                )
                global_validation_warnings.append(code_warn)
                unsupported_claims.append({
                    "type": "HISTORICAL_CASE",
                    "incident_code": code,
                    "grounding_status": "UNVERIFIED_INCIDENT_CODE",
                    "reason": "Incident code does not exist in supplied evidence package."
                })
        elif e_id in evidence_id_map and evidence_id_map[e_id].incident_code:
            matched_item = evidence_id_map[e_id]
            sanitized_cases.append(HistoricalCaseReference(
                incident_code=matched_item.incident_code,
                evidence_id=e_id,
                failure_category=matched_item.failure_category or "CORROBORATED",
                similarity_score=float(matched_item.retrieval_score or 0.0),
                relevance_notes=str(c.get("relevance_notes", "Corroborated historical incident.")),
                metadata_verified=True,
                validation_warnings=[]
            ))
        else:
            if e_id and e_id not in valid_ids:
                hallucinated_citations.append(e_id)
                e_warn = f"Historical case cited invalid evidence ID '{e_id}'."
                global_validation_warnings.append(e_warn)

    # 3. Validate Investigations
    raw_investigations = raw_data.get("recommended_investigations", [])
    sanitized_investigations: List[InvestigationStep] = []
    for idx, inv in enumerate(raw_investigations, start=1):
        sanitized_investigations.append(InvestigationStep(
            step_number=inv.get("step_number", idx),
            target_hypothesis=str(inv.get("target_hypothesis", "Primary hypothesis verification")),
            action=str(inv.get("action", "Inspect component logs and service health metrics")),
            expected_outcome=str(inv.get("expected_outcome", "Determination of component availability"))
        ))

    # Ensure diagnostic investigations prioritize identifying null value, tracing source, and verifying transaction behavior
    has_null_diag = any(
        re.search(r"\b(null|source|origin|transaction|rollback)\b", inv.action + " " + inv.target_hypothesis, re.I)
        for inv in sanitized_investigations
    )
    incident_has_null_or_tx = bool(re.search(
        r"\b(null|nullpointer|npe|nil|transaction|rollback|try[-_\s]?catch)\b",
        str(raw_data) + " " + str([e.snippet for e in evidence_items]),
        re.I
    ))
    if incident_has_null_or_tx and not has_null_diag:
        sanitized_investigations.insert(0, InvestigationStep(
            step_number=1,
            target_hypothesis="Null Value Source Identification & Transaction Behavior Verification",
            action="Identify the specific null reference, trace its origin source (e.g. uninitialized variable, missing database entity, or configuration parameter), and verify whether transaction rollback is the expected consistency behavior.",
            expected_outcome="Exact source of null value established and confirmed whether rollback preserves data integrity before proposing code changes."
        ))
        for s_idx, inv in enumerate(sanitized_investigations, start=1):
            inv.step_number = s_idx

    # 4. Validate Remediation Suggestions (Enforce Advisory-Only & Citation Grounding)
    raw_remediations = raw_data.get("remediation_suggestions", [])
    sanitized_remediations: List[RemediationSuggestion] = []

    for idx, rem in enumerate(raw_remediations, start=1):
        rem_action = str(rem.get("action", "Apply configuration correction or dependency retry"))
        rem_rationale = str(rem.get("rationale", "Addresses root cause identified in primary log evidence"))
        rem_supp = rem.get("supporting_evidence", [])
        rem_warnings: List[str] = []
        rem_grounded = True
        clean_rem_supp: List[str] = []

        if rem_supp:
            for cite in rem_supp:
                total_citations_checked += 1
                cite_str = str(cite).strip().upper()
                if cite_str in valid_ids:
                    clean_rem_supp.append(cite_str)
                    valid_citations_count += 1
                    syntactically_valid_citations_count += 1
                else:
                    hallucinated_citations.append(cite_str)
                    rem_warn = (
                        f"Remediation #{idx} ('{rem_action[:50]}...') cited invalid evidence ID '{cite_str}'. "
                        "Invalid evidence IDs are never substituted with fallback citations."
                    )
                    rem_warnings.append(rem_warn)
                    global_validation_warnings.append(rem_warn)
                    rem_grounded = False

        # Enforce Grounding Invariant: A remediation without validated supporting evidence must NOT be marked grounded!
        if not clean_rem_supp:
            rem_grounded = False
            missing_supp_warn = (
                f"Remediation #{idx} ('{rem_action[:50]}...') provided no validated supporting evidence citations. "
                "Marked as unsupported; strictly requires human review before operational consideration."
            )
            rem_warnings.append(missing_supp_warn)
            global_validation_warnings.append(missing_supp_warn)
            unsupported_claims.append({
                "type": "REMEDIATION",
                "rank": idx,
                "action": rem_action,
                "grounding_status": "UNSUPPORTED_MISSING_CITATION" if not rem_supp else "UNSUPPORTED_INVALID_CITATION",
                "reason": missing_supp_warn
            })

        # If remediation corresponds to an ungrounded hypothesis rank, flag it
        if idx <= len(sanitized_hypotheses) and not sanitized_hypotheses[idx - 1].is_grounded:
            target_h = sanitized_hypotheses[idx - 1]
            h_dep_warn = (
                f"Remediation #{idx} addresses hypothesis #{target_h.rank} which is marked {target_h.grounding_status}. "
                "Remediation premise is unverified."
            )
            rem_warnings.append(h_dep_warn)
            rem_grounded = False
            if not any(c.get("type") == "REMEDIATION" and c.get("rank") == idx for c in unsupported_claims):
                unsupported_claims.append({
                    "type": "REMEDIATION",
                    "rank": idx,
                    "action": rem_action,
                    "grounding_status": "UNGROUNDED_REMEDIATION",
                    "reason": h_dep_warn
                })

        # Issue 2: Defense against try-catch anti-pattern on null-pointer / transaction errors
        is_try_catch = bool(re.search(
            r"\b(try[-_\s]?catch|catch\s+exception|catch\s+nullpointer|catch\s+all|swallow\s+exception|suppress\s+error|catch\s+block)\b",
            rem_action + " " + rem_rationale,
            re.I
        ))
        if is_try_catch:
            tc_warn = (
                f"Remediation #{idx} proposes exception handling (try-catch) to prevent errors or rollbacks. "
                "Exception handling alone does not establish the correct fix. Diagnostic steps that identify "
                "the null value, establish its source, and verify transaction behavior must be prioritized before proposing code changes."
            )
            rem_warnings.append(tc_warn)
            global_validation_warnings.append(tc_warn)
            if "does not establish the correct fix" not in rem_rationale.lower():
                rem_rationale = (
                    f"{rem_rationale} (Caution: Exception handling alone does not establish the correct fix. "
                    "Diagnostic steps must first identify the null value, establish its source, and verify transaction behavior "
                    "before proposing code changes.)"
                )

        sanitized_remediations.append(RemediationSuggestion(
            rank=rem.get("rank", idx),
            action=rem_action,
            rationale=rem_rationale,
            prerequisites=[str(p) for p in rem.get("prerequisites", ["Verify current environment state"])],
            validation_steps=[str(v) for v in rem.get("validation_steps", ["Execute validation build/test suite"])],
            is_advisory_only=True,
            supporting_evidence=clean_rem_supp,
            is_grounded=rem_grounded,
            validation_warnings=rem_warnings
        ))

    # 5. Handle Limited Evidence & Uncertainties
    uncertainties = [str(u) for u in raw_data.get("uncertainties", [])]
    if len(evidence_items) <= 1:
        limited_note = (
            "Limited Evidence: No historical incidents were retrieved from the knowledge base. "
            "Report relies exclusively on the primary incident snippet (E1)."
        )
        if limited_note not in uncertainties:
            uncertainties.insert(0, limited_note)

    # Always disclose semantic verification limitations
    if DISCLOSURE_ENTAILMENT_LIMITATION not in uncertainties:
        uncertainties.append(DISCLOSURE_ENTAILMENT_LIMITATION)

    unique_hallucinations = sorted(list(set(hallucinated_citations)))
    unique_unverified_codes = sorted(list(set(unverified_incident_codes)))

    validation_details = {
        "total_citations_checked": total_citations_checked,
        "syntactically_valid_citations_count": syntactically_valid_citations_count,
        "evidentially_supported_citations_count": evidentially_supported_citations_count,
        "valid_citations_count": valid_citations_count,
        "hallucinated_citations": unique_hallucinations,
        "unverified_incident_codes": unique_unverified_codes,
        "metadata_mismatches": metadata_mismatches,
        "unsupported_claims_count": len(unsupported_claims),
        "grounding_passed": (
            len(unique_hallucinations) == 0 and
            len(unique_unverified_codes) == 0 and
            len(unsupported_claims) == 0 and
            len(metadata_mismatches) == 0
        ),
        "evidence_package_size": len(evidence_items),
        "semantic_verification_method": (
            "Heuristic token overlap and diagnostic keyword analysis "
            "(uncalibrated proxy, not formal NLI entailment)"
        )
    }

    report = SynthesisReport(
        incident_summary=str(raw_data.get("incident_summary", "Incident analysis completed.")),
        predicted_failure_category=str(raw_data.get("predicted_failure_category", classifier_prediction.get("predicted_category", "UNKNOWN"))),
        classifier_info=classifier_prediction,
        likely_root_causes=sanitized_hypotheses,
        evidence=evidence_items,
        recommended_investigations=sanitized_investigations,
        remediation_suggestions=sanitized_remediations,
        uncertainties=uncertainties,
        historical_cases=sanitized_cases,
        human_review_required=True,
        validation_warnings=global_validation_warnings,
        unsupported_claims=unsupported_claims
    )

    return report, validation_details
