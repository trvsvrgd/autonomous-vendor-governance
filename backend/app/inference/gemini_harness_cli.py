"""Executable Gemini Harness Bridge CLI reading structured prompt from stdin and writing strict JSON to stdout."""
import difflib
import json
import os
import re
import sys
from typing import Any

from app.models import MaterialityLevel
from app.schemas import (
    DetectedAgenticChangesSchema,
    DetectedModelChangesSchema,
    GeminiEvaluationResultSchema,
)


def _analyze_snapshot_diff_deterministically(contract: dict[str, Any]) -> GeminiEvaluationResultSchema:
    baseline = contract.get("baseline_state") or {}
    new_text = str(contract.get("new_snapshot_text") or "")
    prev_text = str(baseline.get("previous_snapshot_text") or "")
    is_initial = bool(baseline.get("is_initial_baseline", not bool(prev_text)))
    capabilities = baseline.get("current_capabilities") or []
    current_cap = capabilities[0] if capabilities else {}

    lower_new = new_text.lower()
    lower_prev = prev_text.lower()

    # Detect model family & provider mentions in the new text
    model_patterns = [
        ("Claude 4.5 Sonnet", "Anthropic"),
        ("Claude 3.7 Sonnet", "Anthropic"),
        ("Claude 3.5 Sonnet", "Anthropic"),
        ("GPT-5", "OpenAI"),
        ("GPT-4o", "OpenAI"),
        ("o3-mini", "OpenAI"),
        ("Gemini 2.5 Pro", "Google DeepMind"),
        ("Gemini 2.5 Flash", "Google DeepMind"),
        ("Llama 4", "Meta"),
        ("Llama 3.3 70B", "Meta"),
        ("DeepSeek-R1", "DeepSeek"),
        ("Mistral Large 2", "Mistral AI"),
    ]
    prev_model = current_cap.get("foundation_model_family")
    prev_provider = current_cap.get("model_provider")
    detected_model = prev_model
    detected_provider = prev_provider
    fourth_party_added: list[str] = []

    for m_family, m_prov in model_patterns:
        if m_family.lower() in lower_new:
            detected_model = m_family
            detected_provider = m_prov
            if m_family.lower() not in lower_prev and prev_model and prev_model.lower() != m_family.lower():
                if m_prov not in fourth_party_added:
                    fourth_party_added.append(m_prov)
            break

    model_swapped = bool(
        prev_model
        and detected_model
        and prev_model.lower() != detected_model.lower()
        and not is_initial
    )

    hosting_geo_changed = bool(
        not is_initial
        and any(
            phrase in lower_new and phrase not in lower_prev
            for phrase in (
                "eu-central-1",
                "ap-northeast-1",
                "multi-region cross-border",
                "offshore inference",
                "non-us hosting",
                "hosting geography",
            )
        )
    )

    # Data retention and training detection
    trains_on_data = bool(
        any(
            phrase in lower_new
            for phrase in (
                "trains on customer data",
                "train models on customer inputs",
                "use customer prompts for model training",
                "fine-tune foundation models using customer",
                "opt-out required for model training",
            )
        )
        and "does not train on customer" not in lower_new
    )
    prev_trains = bool(current_cap.get("trains_on_customer_data", False))
    trains_changed = (not is_initial) and (trains_on_data != prev_trains)

    retention_match = re.search(r"retain[a-z\s]*for\s+(\d+)\s+days", lower_new)
    prev_retention = int(current_cap.get("data_retention_days", 0) or 0)
    new_retention = int(retention_match.group(1)) if retention_match else prev_retention
    if "zero data retention" in lower_new or "0 days retention" in lower_new:
        new_retention = 0

    zdr_removed = bool(
        not is_initial
        and ("zero data retention" in lower_prev or prev_retention == 0)
        and (new_retention > 0 or trains_on_data)
    )
    retention_changed = (not is_initial) and (new_retention != prev_retention)

    # Agentic capabilities detection
    mcp_intro = bool(
        ("model context protocol" in lower_new or "mcp server" in lower_new)
        and ("model context protocol" not in lower_prev and "mcp server" not in lower_prev)
    )
    a2a_intro = bool(
        ("agent-to-agent" in lower_new or "a2a protocol" in lower_new or "multi-agent autonomous" in lower_new)
        and ("agent-to-agent" not in lower_prev and "a2a protocol" not in lower_prev)
    )
    tool_intro = bool(
        ("tool calling" in lower_new or "external tool invocation" in lower_new or "function calling" in lower_new)
        and ("tool calling" not in lower_prev and "external tool invocation" not in lower_prev)
    )
    auto_exec_intro = bool(
        ("autonomous execution" in lower_new or "autonomous agent" in lower_new or "unattended action" in lower_new)
        and ("autonomous execution" not in lower_prev and "autonomous agent" not in lower_prev)
    )
    sandbox_changed = bool(
        ("code execution sandbox" in lower_new or "container runtime" in lower_new)
        and ("code execution sandbox" not in lower_prev)
    )

    prev_autonomy = current_cap.get("autonomy_classification", "deterministic")
    new_autonomy = prev_autonomy
    if a2a_intro or "multi-agent" in lower_new:
        new_autonomy = "multi_agent_autonomous"
    elif mcp_intro or tool_intro or auto_exec_intro:
        new_autonomy = "tool_calling_agent"
    elif "copilot" in lower_new or "assistive" in lower_new:
        new_autonomy = "assistive_copilot"

    impacted_risks: list[str] = []
    if mcp_intro or a2a_intro:
        impacted_risks.extend(["FINOS-OP-08", "FINOS-SEC-05", "FINOS-SEC-07"])
    if auto_exec_intro or tool_intro:
        impacted_risks.extend(["FINOS-SEC-01", "FINOS-SEC-05", "FINOS-SEC-08", "FINOS-OP-05"])
    if sandbox_changed:
        impacted_risks.append("FINOS-SEC-09")
    if model_swapped or hosting_geo_changed or fourth_party_added:
        impacted_risks.extend(["FINOS-SEC-06", "FINOS-REG-02", "FINOS-OP-02", "FINOS-OP-01"])
    if trains_on_data or trains_changed or zdr_removed or retention_changed:
        impacted_risks.extend(["FINOS-REG-01", "FINOS-SEC-02", "FINOS-REG-03"])

    # Deduplicate while preserving order
    dedup_risks: list[str] = []
    for r in impacted_risks:
        if r not in dedup_risks:
            dedup_risks.append(r)

    is_material = any(
        [
            model_swapped,
            hosting_geo_changed,
            bool(fourth_party_added),
            trains_changed,
            trains_on_data,
            zdr_removed,
            retention_changed,
            mcp_intro,
            a2a_intro,
            tool_intro,
            auto_exec_intro,
            sandbox_changed,
        ]
    )

    diff_lines = list(
        difflib.unified_diff(
            prev_text.splitlines(),
            new_text.splitlines(),
            lineterm="",
            n=1,
        )
    )
    added_lines = [
        line[1:].strip()
        for line in diff_lines
        if line.startswith("+") and not line.startswith("+++") and line[1:].strip()
    ]
    change_snippet = "; ".join(added_lines[:3]) if added_lines else new_text[:240].strip()

    vendor_name = baseline.get("vendor_legal_name", "Vendor")
    if is_material:
        mat_level = MaterialityLevel.material
        exec_summary = (
            f"MATERIAL SHIFT DETECTED for {vendor_name}: Analysis of captured disclosure snapshot "
            f"identified high-impact governance modifications ({change_snippet[:220]}). "
            f"Triggered {len(dedup_risks)} FINOS AI Governance Framework v2 risk controls: "
            f"{', '.join(dedup_risks)}."
        )
        rec_actions = (
            "1. Hold production deployment of updated capability pending Business Owner & Model Risk signoff.\n"
            "2. Request updated third-party AI Addendum / Zero Data Retention attestation and MCP/A2A security architecture review.\n"
            "3. Update SR 11-7 Model Inventory and EU AI Act GPAI technical documentation."
        )
    elif is_initial:
        mat_level = MaterialityLevel.baseline
        if not dedup_risks:
            dedup_risks = ["FINOS-REG-02"]
        exec_summary = (
            f"Initial baseline snapshot established for {vendor_name}. "
            f"Detected model family '{detected_model or 'Unspecified'}' with autonomy level '{new_autonomy}' "
            f"and {new_retention}-day data retention policy."
        )
        rec_actions = (
            "Verify baseline AI capability inventory attributes and confirm recurring EventBridge polling schedule."
        )
    else:
        mat_level = MaterialityLevel.non_material
        exec_summary = (
            f"NON-MATERIAL UPDATE for {vendor_name}: Snapshot diff is restricted to minor documentation, "
            f"UI/latency, or operational notes ({change_snippet[:180]}) without altering foundation model "
            f"weights, agentic autonomy boundaries, or customer data retention rights."
        )
        rec_actions = (
            "Include in scheduled Non-Material Business Owner Digest; no immediate escalation required."
        )

    return GeminiEvaluationResultSchema(
        materiality_level=mat_level,
        executive_summary=exec_summary,
        detected_model_changes=DetectedModelChangesSchema(
            previous_model_family=prev_model,
            new_model_family=detected_model,
            previous_model_provider=prev_provider,
            new_model_provider=detected_provider,
            previous_hosting_topology=current_cap.get("hosting_topology", "vendor_hosted"),
            new_hosting_topology=current_cap.get("hosting_topology", "vendor_hosted"),
            fourth_party_providers_added=fourth_party_added,
            hosting_geography_changed=hosting_geo_changed,
            model_family_swapped=model_swapped,
            trains_on_customer_data_changed=trains_changed,
            trains_on_customer_data=trains_on_data,
            data_retention_changed=retention_changed,
            new_data_retention_days=new_retention,
            zero_data_retention_removed=zdr_removed,
        ),
        detected_agentic_changes=DetectedAgenticChangesSchema(
            previous_autonomy_classification=prev_autonomy,
            new_autonomy_classification=new_autonomy,
            autonomous_execution_introduced=auto_exec_intro,
            external_tool_invocation_introduced=tool_intro,
            mcp_server_introduced=mcp_intro,
            a2a_communication_introduced=a2a_intro,
            sandbox_or_code_execution_changed=sandbox_changed,
            summary_of_agentic_shifts=(
                "Introduced autonomous/MCP/A2A agentic execution capabilities."
                if (mcp_intro or a2a_intro or tool_intro or auto_exec_intro)
                else "No change to agentic autonomy boundary."
            ),
        ),
        impacted_finos_risk_ids=dedup_risks,
        finos_severity_increased=is_material,
        recommended_actions=rec_actions,
        gemini_model_identifier="gemini-2.5-pro (harness-bridge)",
    )


def main() -> int:
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        sys.stderr.write("Empty prompt received on stdin.\n")
        return 1

    contract = json.loads(raw_input)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        try:
            from google import genai
            from google.genai import types as genai_types

            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(
                model=os.environ.get("GEMINI_MODEL_ID", "gemini-2.5-pro"),
                contents=raw_input,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiEvaluationResultSchema,
                    temperature=0.0,
                ),
            )
            if resp.text:
                sys.stdout.write(resp.text)
                return 0
        except Exception as exc:
            sys.stderr.write(f"Live Gemini SDK fallback in harness CLI: {exc}\n")

    result = _analyze_snapshot_diff_deterministically(contract)
    sys.stdout.write(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
