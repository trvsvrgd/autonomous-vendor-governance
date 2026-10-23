import json
import logging
import os
import re
import subprocess
import sys
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.aws_clients import fetch_secret_json
from app.config import get_settings
from app.models import MaterialityLevel
from app.schemas import GeminiEvaluationResultSchema

logger = logging.getLogger(__name__)


class GeminiGovernanceEvaluator:
    """Pluggable Gemini Harness Bridge and FINOS v2 Materiality Engine.

    Exposes a single public method `evaluateVendorDiff(baselineState, newSnapshotText, finosCatalog)`
    that routes inference via the local Gemini harness subprocess (`GEMINI_EXECUTION_MODE=harness`)
    or via the official Google Gen AI SDK (`GEMINI_EXECUTION_MODE=api` or `vertex`) using credentials
    fetched at runtime from AWS Secrets Manager.
    """

    def evaluateVendorDiff(
        self,
        baselineState: dict[str, Any],
        newSnapshotText: str,
        finosCatalog: list[dict[str, Any]],
    ) -> GeminiEvaluationResultSchema:
        settings = get_settings()
        execution_mode = settings.GEMINI_EXECUTION_MODE

        structured_prompt = self._build_prompt_contract(
            baseline_state=baselineState,
            new_snapshot_text=newSnapshotText,
            finos_catalog=finosCatalog,
        )

        if execution_mode == "harness":
            raw_json_payload = self._invoke_harness_subprocess(structured_prompt)
        elif execution_mode in ("api", "vertex"):
            raw_json_payload = self._invoke_google_genai_sdk(
                structured_prompt, mode=execution_mode
            )
        else:
            raise ValueError(f"Unsupported GEMINI_EXECUTION_MODE: {execution_mode}")

        validated_result = self._validate_and_enforce_deterministic_rules(
            raw_payload=raw_json_payload,
            baseline_state=baselineState,
            new_snapshot_text=newSnapshotText,
            finos_catalog=finosCatalog,
        )
        return validated_result

    def _build_prompt_contract(
        self,
        *,
        baseline_state: dict[str, Any],
        new_snapshot_text: str,
        finos_catalog: list[dict[str, Any]],
    ) -> str:
        catalog_summary = [
            {
                "risk_id": item["risk_id"],
                "category_group": item["category_group"],
                "risk_name": item["risk_name"],
                "default_severity": item.get("default_severity", "HIGH"),
                "description": item["description"],
            }
            for item in finos_catalog
        ]

        prompt_contract = {
            "role": "FINOS_AI_GOVERNANCE_V2_AUDITOR",
            "instructions": (
                "Evaluate the vendor snapshot diff against the baseline state and the 23 official "
                "FINOS AI Governance Framework v2 risk controls. Return ONLY a strict JSON object "
                "conforming to GeminiEvaluationResultSchema. "
                "DETERMINISTIC MATERIALITY RULES: Classify as 'material' if ANY of the following occur: "
                "(1) Vendor introduces autonomous agentic execution, external tool invocation, Model Context Protocol (MCP) servers, or Agent-to-Agent (A2A) communication. "
                "(2) Vendor swaps the underlying foundation model family, changes model hosting geography, or adds a new fourth-party model provider. "
                "(3) Vendor alters ULA or policy language regarding customer data retention, zero data retention (ZDR) guarantees, or training models on customer inputs. "
                "(4) The update increases severity exposure on any of the 23 FINOS risk controls. "
                "Classify as 'non_material' ONLY if changes are limited to UI adjustments, minor latency improvements, documentation formatting, or bug fixes that do not alter model weights, agent autonomy, or data rights. "
                "If baselineState has is_initial_baseline=true and no material policy violations are introduced, classify as 'baseline' (or 'material' if critical agentic/training risks are present)."
            ),
            "baseline_state": baseline_state,
            "new_snapshot_text": new_snapshot_text[:32000],
            "finos_v2_catalog": catalog_summary,
            "required_json_schema": GeminiEvaluationResultSchema.model_json_schema(),
        }
        return json.dumps(prompt_contract, indent=2, default=str)

    def _invoke_harness_subprocess(self, structured_prompt: str) -> dict[str, Any]:
        """Invoke the local Gemini harness CLI or MCP server subprocess via stdin/stdout."""
        settings = get_settings()
        harness_cmd = settings.GEMINI_HARNESS_COMMAND.strip()
        cmd_parts = harness_cmd.split()
        if cmd_parts and cmd_parts[0] in ("python", "python3"):
            cmd_parts[0] = sys.executable

        proc = subprocess.run(
            cmd_parts,
            input=structured_prompt,
            capture_output=True,
            text=True,
            timeout=settings.GEMINI_HARNESS_TIMEOUT_SECONDS,
            check=False,
        )
        stdout_text = (proc.stdout or "").strip()
        if proc.returncode != 0 or not stdout_text:
            raise RuntimeError(
                f"Gemini harness subprocess '{harness_cmd}' exited with code {proc.returncode}: "
                f"{(proc.stderr or '').strip()}"
            )
        return self._extract_json_object(stdout_text)

    def _invoke_google_genai_sdk(
        self, structured_prompt: str, *, mode: str
    ) -> dict[str, Any]:
        """Invoke the official Google Gen AI SDK using credentials fetched from AWS Secrets Manager."""
        settings = get_settings()
        secret_creds = fetch_secret_json(settings.AWS_SECRETS_GEMINI_SECRET_ID)

        if mode == "vertex":
            project_id = (
                secret_creds.get("vertex_project_id")
                or settings.VERTEX_PROJECT_ID
                or os.environ.get("GOOGLE_CLOUD_PROJECT")
            )
            location = (
                secret_creds.get("vertex_location")
                or settings.VERTEX_LOCATION
                or "us-central1"
            )
            if not project_id:
                raise RuntimeError(
                    "Vertex AI execution mode requires 'vertex_project_id' in AWS Secrets Manager "
                    "or VERTEX_PROJECT_ID environment variable."
                )
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
            )
        else:
            api_key = (
                secret_creds.get("gemini_api_key")
                or secret_creds.get("GEMINI_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
            )
            if not api_key:
                raise RuntimeError(
                    "API execution mode requires 'gemini_api_key' in AWS Secrets Manager "
                    f"({settings.AWS_SECRETS_GEMINI_SECRET_ID}) or GEMINI_API_KEY environment variable."
                )
            client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL_ID,
            contents=structured_prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiEvaluationResultSchema,
                temperature=0.0,
            ),
        )
        raw_text = response.text or ""
        return self._extract_json_object(raw_text)

    def _extract_json_object(self, raw_text: str) -> dict[str, Any]:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            raise ValueError("Gemini output did not contain a valid JSON object.")
        return json.loads(cleaned[start_idx : end_idx + 1])

    def _validate_and_enforce_deterministic_rules(
        self,
        *,
        raw_payload: dict[str, Any],
        baseline_state: dict[str, Any],
        new_snapshot_text: str,
        finos_catalog: list[dict[str, Any]],
    ) -> GeminiEvaluationResultSchema:
        """Validate response against GeminiEvaluationResultSchema and enforce deterministic FINOS v2 rules."""
        settings = get_settings()
        if "gemini_model_identifier" not in raw_payload or not raw_payload["gemini_model_identifier"]:
            raw_payload["gemini_model_identifier"] = (
                f"{settings.GEMINI_MODEL_ID} ({settings.GEMINI_EXECUTION_MODE})"
            )

        result = GeminiEvaluationResultSchema.model_validate(raw_payload)
        valid_finos_ids = {item["risk_id"] for item in finos_catalog}
        impacted_ids = [rid for rid in result.impacted_finos_risk_ids if rid in valid_finos_ids]

        mc = result.detected_model_changes
        ac = result.detected_agentic_changes

        # Check the 4 deterministic materiality triggers required by Section 4:
        # Condition 1: Autonomous agentic execution, external tool invocation, MCP servers, or A2A communication
        cond_agentic = any(
            [
                ac.autonomous_execution_introduced,
                ac.external_tool_invocation_introduced,
                ac.mcp_server_introduced,
                ac.a2a_communication_introduced,
                ac.sandbox_or_code_execution_changed,
            ]
        )
        if cond_agentic:
            for code in ("FINOS-OP-08", "FINOS-SEC-05", "FINOS-SEC-08"):
                if code in valid_finos_ids and code not in impacted_ids:
                    impacted_ids.append(code)

        # Condition 2: Swaps foundation model family, changes hosting geography, or adds 4th-party model provider
        cond_model_or_supply_chain = any(
            [
                mc.model_family_swapped,
                mc.hosting_geography_changed,
                len(mc.fourth_party_providers_added) > 0,
            ]
        )
        if cond_model_or_supply_chain:
            for code in ("FINOS-SEC-06", "FINOS-REG-02", "FINOS-OP-02"):
                if code in valid_finos_ids and code not in impacted_ids:
                    impacted_ids.append(code)

        # Condition 3: Alters ULA or policy language regarding customer data retention, ZDR, or training on customer inputs
        cond_data_rights = any(
            [
                mc.trains_on_customer_data_changed,
                mc.trains_on_customer_data is True,
                mc.data_retention_changed,
                mc.zero_data_retention_removed,
            ]
        )
        if cond_data_rights:
            for code in ("FINOS-REG-01", "FINOS-SEC-02", "FINOS-REG-03"):
                if code in valid_finos_ids and code not in impacted_ids:
                    impacted_ids.append(code)

        # Condition 4: Increases severity exposure on any of the 23 FINOS risk controls
        cond_finos_severity = result.finos_severity_increased

        # Also inspect the raw text diff deterministically so no material shift can slip through
        prev_text = str(baseline_state.get("previous_snapshot_text") or "").lower()
        curr_text = new_snapshot_text.lower()
        if prev_text and prev_text != curr_text:
            if ("model context protocol" in curr_text or "mcp server" in curr_text) and (
                "model context protocol" not in prev_text and "mcp server" not in prev_text
            ):
                ac.mcp_server_introduced = True
                cond_agentic = True
                if "FINOS-OP-08" not in impacted_ids:
                    impacted_ids.append("FINOS-OP-08")
            if ("agent-to-agent" in curr_text or "a2a" in curr_text) and (
                "agent-to-agent" not in prev_text and "a2a" not in prev_text
            ):
                ac.a2a_communication_introduced = True
                cond_agentic = True
                if "FINOS-OP-08" not in impacted_ids:
                    impacted_ids.append("FINOS-OP-08")
            if (
                (
                    "trains on customer" in curr_text
                    or "train models on customer" in curr_text
                    or "model training on customer inputs" in curr_text
                    or "retain customer prompts for 90 days" in curr_text
                    or "retain customer data for" in curr_text
                )
                and "does not train on customer" not in curr_text
                and (
                    "zero data retention" in prev_text
                    or "does not train on customer" in prev_text
                )
            ):
                mc.trains_on_customer_data_changed = True
                mc.zero_data_retention_removed = True
                cond_data_rights = True
                if "FINOS-REG-01" not in impacted_ids:
                    impacted_ids.append("FINOS-REG-01")

        result.impacted_finos_risk_ids = impacted_ids

        if cond_agentic or cond_model_or_supply_chain or cond_data_rights or cond_finos_severity:
            result.materiality_level = MaterialityLevel.material
            result.finos_severity_increased = True
        elif baseline_state.get("is_initial_baseline") and result.materiality_level != MaterialityLevel.material:
            result.materiality_level = MaterialityLevel.baseline

        return result
