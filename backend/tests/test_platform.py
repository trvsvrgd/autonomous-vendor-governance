import io
import pytest
from app.finos.catalog import FINOS_V2_RISK_CATALOG
from app.inference.gemini_evaluator import GeminiGovernanceEvaluator
from app.models import MaterialityLevel
from app.workers.safe_fetch import (
    SSRFProtectionError,
    compute_normalized_sha256,
    normalize_and_extract_html_text,
    validate_ip_ssrf_safe,
    validate_url_ssrf_safe,
)


def test_finos_v2_catalog_contains_23_official_risks():
    assert len(FINOS_V2_RISK_CATALOG) == 23
    op_risks = [r for r in FINOS_V2_RISK_CATALOG if r["category_group"] == "operational"]
    sec_risks = [r for r in FINOS_V2_RISK_CATALOG if r["category_group"] == "security"]
    reg_risks = [
        r for r in FINOS_V2_RISK_CATALOG if r["category_group"] == "regulatory_compliance"
    ]
    assert len(op_risks) == 11
    assert len(sec_risks) == 9
    assert len(reg_risks) == 3


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8080/admin",
        "http://localhost/internal",
        "http://10.0.0.15/secret",
        "http://192.168.1.1/router",
        "http://172.16.5.4/internal",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
    ],
)
def test_ssrf_safe_fetch_blocks_private_and_metadata_endpoints(blocked_url: str):
    with pytest.raises(SSRFProtectionError):
        validate_url_ssrf_safe(blocked_url)


def test_public_ip_passes_ssrf_validation():
    validate_ip_ssrf_safe("8.8.8.8")
    validate_ip_ssrf_safe("1.1.1.1")


def test_dom_boilerplate_stripping_and_sha256():
    html_a = """
    <html>
      <head><script>console.log('tracking');</script></head>
      <body>
        <nav>Top Navigation Menu</nav>
        <header>Marketing Header v1</header>
        <main>
          <h1>Enterprise AI Trust Center</h1>
          <p>Zero Data Retention is enforced for all enterprise customers.</p>
        </main>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    html_b = """
    <html>
      <body>
        <nav>Changed Navigation Links</nav>
        <main>
          <h1>Enterprise AI Trust Center</h1>
          <p>Zero Data Retention is enforced for all enterprise customers.</p>
        </main>
        <footer>Updated Footer 2027</footer>
      </body>
    </html>
    """
    norm_a = normalize_and_extract_html_text(html_a)
    norm_b = normalize_and_extract_html_text(html_b)
    assert norm_a == norm_b
    assert compute_normalized_sha256(norm_a) == compute_normalized_sha256(norm_b)


def test_gemini_governance_evaluator_harness_material_and_non_material():
    evaluator = GeminiGovernanceEvaluator()
    baseline_state = {
        "vendor_id": "00000000-0000-0000-0000-000000000001",
        "vendor_legal_name": "Anthropic PBC",
        "primary_domain": "anthropic.com",
        "risk_tier": "critical",
        "is_initial_baseline": False,
        "previous_snapshot_text": (
            "Anthropic Enterprise Trust Center: Uses Claude 3.7 Sonnet on AWS Bedrock. "
            "Zero data retention (0 days). Does not train on customer data."
        ),
        "current_capabilities": [
            {
                "foundation_model_family": "Claude 3.7 Sonnet",
                "model_provider": "Anthropic",
                "hosting_topology": "aws_bedrock",
                "autonomy_classification": "assistive_copilot",
                "mcp_or_a2a_enabled": False,
                "trains_on_customer_data": False,
                "data_retention_days": 0,
            }
        ],
    }

    # 1. Material Change: Introduces MCP servers, A2A protocol, model swap to GPT-5, and 90-day retention
    material_snapshot = (
        "Product & Policy Update: Switched foundation model to GPT-5 (OpenAI). "
        "Introduced autonomous execution via Model Context Protocol (MCP) servers and "
        "Agent-to-Agent (A2A) protocol. We now retain customer data for 90 days and "
        "train models on customer inputs unless opted out."
    )
    mat_result = evaluator.evaluateVendorDiff(
        baselineState=baseline_state,
        newSnapshotText=material_snapshot,
        finosCatalog=FINOS_V2_RISK_CATALOG,
    )
    assert mat_result.materiality_level == MaterialityLevel.material
    assert mat_result.detected_agentic_changes.mcp_server_introduced is True
    assert mat_result.detected_agentic_changes.a2a_communication_introduced is True
    assert mat_result.detected_model_changes.trains_on_customer_data is True
    assert "FINOS-OP-08" in mat_result.impacted_finos_risk_ids
    assert "FINOS-REG-01" in mat_result.impacted_finos_risk_ids

    # 2. Non-Material Change: Minor UI & dark mode latency fix
    non_material_snapshot = (
        "Anthropic Enterprise Trust Center: Uses Claude 3.7 Sonnet on AWS Bedrock. "
        "Zero data retention (0 days). Does not train on customer data. "
        "Release Note v2.1.4: Minor UI typography adjustment and 15ms dark-mode rendering fix."
    )
    non_mat_result = evaluator.evaluateVendorDiff(
        baselineState=baseline_state,
        newSnapshotText=non_material_snapshot,
        finosCatalog=FINOS_V2_RISK_CATALOG,
    )
    assert non_mat_result.materiality_level == MaterialityLevel.non_material
