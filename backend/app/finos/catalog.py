from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import FinosRiskCategoryGroup, FinosRiskControl

FINOS_V2_RISK_CATALOG: list[dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # Eleven Operational Risks
    # -------------------------------------------------------------------------
    {
        "risk_id": "FINOS-OP-01",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Hallucination and inaccurate outputs",
        "description": (
            "Generation of fabricated, ungrounded, or factually incorrect statements "
            "by foundation models or RAG pipelines impacting enterprise decisions."
        ),
        "default_severity": "HIGH",
        "sr_11_7_mapping": "SR 11-7 Section IV.A (Conceptual Soundness & Output Validation)",
        "nist_ai_rmf_mapping": "MEASURE 2.5 / MANAGE 2.2 (Validity and Reliability)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.4 (AI System Verification & Validation)",
        "eu_ai_act_mapping": "Article 15 (Accuracy, Robustness and Cybersecurity)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-01",
            "control-type": "groundedness-verification",
            "enforcement": "rag-citation-and-factual-threshold",
        },
    },
    {
        "risk_id": "FINOS-OP-02",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Non determinism",
        "description": (
            "Stochastic variance across identical prompts or model weight updates causing "
            "unreproducible workflows in regulated financial or enterprise processes."
        ),
        "default_severity": "MEDIUM",
        "sr_11_7_mapping": "SR 11-7 Section IV.B (Ongoing Monitoring & Benchmark Stability)",
        "nist_ai_rmf_mapping": "MEASURE 2.6 (Reproducibility and Consistency)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.5 (AI System Deployment Controls)",
        "eu_ai_act_mapping": "Article 15(1) (Consistent Performance Across Lifecycle)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-02",
            "control-type": "pinned-model-version-and-seed-control",
            "enforcement": "immutable-model-version-pinning",
        },
    },
    {
        "risk_id": "FINOS-OP-03",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Bias",
        "description": (
            "Systematic demographic, representational, or decision skew in model outputs "
            "resulting in unfair treatment or discriminatory outcomes."
        ),
        "default_severity": "HIGH",
        "sr_11_7_mapping": "SR 11-7 Section IV.C (Outcomes Analysis & Fair Lending Alignment)",
        "nist_ai_rmf_mapping": "MEASURE 2.11 / MANAGE 1.3 (Fairness and Bias Mitigation)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.5.4 (Responsible AI Impact Assessment)",
        "eu_ai_act_mapping": "Article 10(2)(f) (Data Governance Bias Examination)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-03",
            "control-type": "fairness-evaluation-gate",
            "enforcement": "pre-deployment-disparate-impact-audit",
        },
    },
    {
        "risk_id": "FINOS-OP-04",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Explainability gaps",
        "description": (
            "Inability to reconstruct or audit the reasoning path, feature attribution, "
            "or tool-selection rationale behind an AI capability's output."
        ),
        "default_severity": "HIGH",
        "sr_11_7_mapping": "SR 11-7 Section VI (Model Documentation & Auditability)",
        "nist_ai_rmf_mapping": "MEASURE 2.9 (Explainability and Interpretability)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.8.2 (Transparency and Explainability)",
        "eu_ai_act_mapping": "Article 13 (Transparency and Provision of Information to Deployers)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-04",
            "control-type": "telemetry-trace-logging",
            "enforcement": "immutable-chain-of-thought-and-tool-audit-log",
        },
    },
    {
        "risk_id": "FINOS-OP-05",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Model overreach",
        "description": (
            "Invocation of foundation models or agents outside their validated domain boundary "
            "or intended scope of operational authority."
        ),
        "default_severity": "HIGH",
        "sr_11_7_mapping": "SR 11-7 Section III (Model Use Within Intended Scope)",
        "nist_ai_rmf_mapping": "MAP 1.5 / GOVERN 1.2 (Organizational Risk Tolerance & Scope)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.1.2 (Intended Use Specification)",
        "eu_ai_act_mapping": "Article 9(2)(b) (Foreseeable Misuse Evaluation)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-05",
            "control-type": "semantic-topic-guardrail",
            "enforcement": "domain-boundary-input-output-filter",
        },
    },
    {
        "risk_id": "FINOS-OP-06",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Availability",
        "description": (
            "Service degradation, rate-limit exhaustion, or regional outage of upstream "
            "foundation model APIs or hosted inference endpoints."
        ),
        "default_severity": "MEDIUM",
        "sr_11_7_mapping": "SR 11-7 Section V (Operational Resilience & Contingency Planning)",
        "nist_ai_rmf_mapping": "MANAGE 3.1 (Third-Party Dependency Resilience)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.6 (Operational Continuity)",
        "eu_ai_act_mapping": "Article 15(4) (Resilience Against Faults and Inconsistencies)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-06",
            "control-type": "multi-region-failover-circuit-breaker",
            "enforcement": "automated-fallback-routing",
        },
    },
    {
        "risk_id": "FINOS-OP-07",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Data quality",
        "description": (
            "Stale, corrupted, or unverified grounding data fed into vendor context windows, "
            "embeddings, or fine-tuning corpora."
        ),
        "default_severity": "MEDIUM",
        "sr_11_7_mapping": "SR 11-7 Section IV.A.2 (Data Integrity and Relevance)",
        "nist_ai_rmf_mapping": "MAP 2.3 / MEASURE 2.4 (Data Quality and Lineage)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.7 (Data for AI Systems)",
        "eu_ai_act_mapping": "Article 10 (Data and Data Governance)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-07",
            "control-type": "data-lineage-schema-validation",
            "enforcement": "pre-ingestion-data-quality-check",
        },
    },
    {
        "risk_id": "FINOS-OP-08",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Multi agent trust",
        "description": (
            "Cascading errors, unverified delegation, or conflicting objectives across "
            "autonomous multi-agent topologies (MCP or A2A protocols)."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section IV.B (Interdependent Model Network Validation)",
        "nist_ai_rmf_mapping": "MAP 3.4 / MANAGE 3.2 (Complex Emergent Agent Interactions)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.7 (Inter-System AI Interfaces)",
        "eu_ai_act_mapping": "Article 14(4) (Oversight of Interconnected Autonomous Systems)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-08",
            "control-type": "a2a-mutual-tls-and-capability-attestation",
            "enforcement": "cryptographic-agent-identity-and-hop-limit",
        },
    },
    {
        "risk_id": "FINOS-OP-09",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Context window degradation",
        "description": (
            "Loss of instruction adherence or middle-context retrieval recall as prompt "
            "token payloads scale in long-horizon vendor sessions."
        ),
        "default_severity": "MEDIUM",
        "sr_11_7_mapping": "SR 11-7 Section IV.A (Boundary Condition & Stress Testing)",
        "nist_ai_rmf_mapping": "MEASURE 2.5 (Performance Under Context Stress)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.4 (Boundary Verification)",
        "eu_ai_act_mapping": "Article 15(3) (Robustness Under Operational Constraints)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-09",
            "control-type": "context-budget-compaction-guard",
            "enforcement": "token-threshold-alert-and-summarization-verification",
        },
    },
    {
        "risk_id": "FINOS-OP-10",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Latency failure",
        "description": (
            "Inference or agentic reasoning loop timeouts breaching enterprise SLA thresholds "
            "for synchronous operational workflows."
        ),
        "default_severity": "LOW",
        "sr_11_7_mapping": "SR 11-7 Section V (Operational Performance Monitoring)",
        "nist_ai_rmf_mapping": "MEASURE 2.7 (Operational SLA Telemetry)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.6 (Service Level Monitoring)",
        "eu_ai_act_mapping": "Article 15(1) (Operational Performance Reliability)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-10",
            "control-type": "latency-sla-budget",
            "enforcement": "strict-timeout-and-degraded-mode",
        },
    },
    {
        "risk_id": "FINOS-OP-11",
        "category_group": FinosRiskCategoryGroup.operational.value,
        "risk_name": "Human oversight fatigue",
        "description": (
            "Rubber-stamping or degraded operator vigilance due to excessive low-signal alerts "
            "or over-reliance on assistive copilot recommendations."
        ),
        "default_severity": "HIGH",
        "sr_11_7_mapping": "SR 11-7 Section V.A (Governance & Effective Challenge)",
        "nist_ai_rmf_mapping": "GOVERN 3.2 / MANAGE 2.4 (Human-in-the-Loop Effectiveness)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.9.3 (Human Oversight Procedures)",
        "eu_ai_act_mapping": "Article 14 (Human Oversight & Automation Bias Prevention)",
        "calm_control_requirement": {
            "control-id": "calm-finos-op-11",
            "control-type": "materiality-tiered-alert-routing",
            "enforcement": "non-material-digest-aggregation-and-explicit-signoff",
        },
    },
    # -------------------------------------------------------------------------
    # Nine Security Risks
    # -------------------------------------------------------------------------
    {
        "risk_id": "FINOS-SEC-01",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Prompt injection",
        "description": (
            "Direct or indirect adversarial inputs overriding system instructions via "
            "untrusted documents, emails, web pages, or API payloads."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V (Information Security & Adversarial Resilience)",
        "nist_ai_rmf_mapping": "MEASURE 2.7 / MANAGE 2.3 (Adversarial Attack Resilience)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.8 (AI Security Controls)",
        "eu_ai_act_mapping": "Article 15(5) (Resilience Against Unauthorized Manipulation)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-01",
            "control-type": "prompt-injection-classifier-and-privilege-separation",
            "enforcement": "untrusted-data-plane-isolation",
        },
    },
    {
        "risk_id": "FINOS-SEC-02",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Data poisoning",
        "description": (
            "Injection of malicious or backdoored samples into training sets, fine-tuning "
            "pipelines, or continuous feedback loops."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section IV.A.2 (Training Data Provenance & Integrity)",
        "nist_ai_rmf_mapping": "MEASURE 2.7 (Data Poisoning Detection)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.7.4 (Data Provenance Verification)",
        "eu_ai_act_mapping": "Article 15(5) (Data Poisoning Mitigation)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-02",
            "control-type": "corpus-cryptographic-hash-attestation",
            "enforcement": "zero-customer-training-and-curated-corpus-scan",
        },
    },
    {
        "risk_id": "FINOS-SEC-03",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Model tampering",
        "description": (
            "Unauthorized modification of model weights, system prompts, LoRA adapters, "
            "or inference container images in vendor hosting environments."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V.B (Change Control & Model Inventory Integrity)",
        "nist_ai_rmf_mapping": "GOVERN 1.5 / MANAGE 3.1 (Model Artifact Integrity)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.5 (Configuration Management)",
        "eu_ai_act_mapping": "Article 15(5) (Model Integrity Protection)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-03",
            "control-type": "signed-model-weights-and-immutable-registry",
            "enforcement": "slsa-provenance-verification",
        },
    },
    {
        "risk_id": "FINOS-SEC-04",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Vector store leakage",
        "description": (
            "Cross-tenant or unauthorized retrieval of sensitive embeddings and chunks "
            "from shared vector databases or improperly scoped RAG indexes."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V (Data Confidentiality & Access Controls)",
        "nist_ai_rmf_mapping": "MEASURE 2.10 (Privacy and Confidentiality Preservation)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.7.5 (Data Isolation & Access Control)",
        "eu_ai_act_mapping": "Article 10(5) (Secure Processing & Tenant Isolation)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-04",
            "control-type": "row-level-vector-acl-and-kms-encryption",
            "enforcement": "per-tenant-vector-namespace-isolation",
        },
    },
    {
        "risk_id": "FINOS-SEC-05",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Tool manipulation",
        "description": (
            "Coercing a tool-calling agent or MCP client into invoking external APIs, "
            "database mutations, or webhooks with attacker-controlled parameters."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V (Operational & Automated Execution Controls)",
        "nist_ai_rmf_mapping": "MANAGE 2.4 (Agentic Tool Invocation Guardrails)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.8 (Controlled External Action)",
        "eu_ai_act_mapping": "Article 14(4)(d) (Intervention and Stop Controls on Actions)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-05",
            "control-type": "strict-json-schema-tool-parameter-policy",
            "enforcement": "least-privilege-tool-allowlist-and-human-approval",
        },
    },
    {
        "risk_id": "FINOS-SEC-06",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Supply chain compromise",
        "description": (
            "Compromise of fourth-party foundation model providers, open-weight hubs, "
            "MCP server packages, or subprocessor infrastructure."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V.C (Third-Party & Vendor Model Risk Management)",
        "nist_ai_rmf_mapping": "GOVERN 6.1 / GOVERN 6.2 (AI Supply Chain Risk Management)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.10 (Third-Party and Customer Relationships)",
        "eu_ai_act_mapping": "Article 25 / Article 53 (Value Chain & GPAI Provider Obligations)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-06",
            "control-type": "continuous-fourth-party-subprocessor-monitoring",
            "enforcement": "automated-subprocessor-and-model-lineage-diffing",
        },
    },
    {
        "risk_id": "FINOS-SEC-07",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Credential harvesting",
        "description": (
            "Exposure or exfiltration of OAuth tokens, API keys, IAM roles, or session "
            "secrets passed into agent memory, logs, or MCP environment contexts."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V (Privileged Access & Secret Management)",
        "nist_ai_rmf_mapping": "MEASURE 2.7 / MANAGE 2.3 (Credential & Secret Redaction)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.8 (Secret Protection in AI Contexts)",
        "eu_ai_act_mapping": "Article 15(5) (Cybersecurity & Secret Protection)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-07",
            "control-type": "ephemeral-scoped-token-broker",
            "enforcement": "zero-credential-in-prompt-context",
        },
    },
    {
        "risk_id": "FINOS-SEC-08",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Unauthorized agent action",
        "description": (
            "Autonomous agent executing state-changing financial, contractual, or "
            "infrastructure operations without explicit human authorization."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V.A (Governance Authorization & Dual Control)",
        "nist_ai_rmf_mapping": "GOVERN 3.2 / MANAGE 2.4 (Autonomous Action Step Limits & Gates)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.9.3 (Human-in-the-Loop Authorization)",
        "eu_ai_act_mapping": "Article 14(4)(e) (Override and Halt Capability)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-08",
            "control-type": "cryptographic-step-up-approval-gate",
            "enforcement": "mandatory-human-signoff-for-write-actions",
        },
    },
    {
        "risk_id": "FINOS-SEC-09",
        "category_group": FinosRiskCategoryGroup.security.value,
        "risk_name": "Sandbox escape",
        "description": (
            "Code-execution or computer-use agent breaking out of its container/microVM "
            "isolation boundary to access host networks or metadata endpoints."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V (Execution Environment Isolation)",
        "nist_ai_rmf_mapping": "MANAGE 2.3 (Runtime Isolation and Containment)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.6.2.8 (Isolated Execution Environments)",
        "eu_ai_act_mapping": "Article 15(5) (Containment of Autonomous Code Execution)",
        "calm_control_requirement": {
            "control-id": "calm-finos-sec-09",
            "control-type": "microvm-sandbox-and-ssrf-egress-firewall",
            "enforcement": "block-private-cidr-and-imds-egress",
        },
    },
    # -------------------------------------------------------------------------
    # Three Regulatory and Compliance Risks
    # -------------------------------------------------------------------------
    {
        "risk_id": "FINOS-REG-01",
        "category_group": FinosRiskCategoryGroup.regulatory_compliance.value,
        "risk_name": "Information leakage",
        "description": (
            "Retention of customer PII/MNPI or use of enterprise inputs to train or "
            "fine-tune vendor foundation models in violation of zero-data-retention mandates."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section V.C (Confidentiality & Data Rights in Vendor Models)",
        "nist_ai_rmf_mapping": "MEASURE 2.10 / GOVERN 6.1 (Data Retention & Training Opt-Out)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.7.6 (Customer Data Usage & Retention)",
        "eu_ai_act_mapping": "Article 10(5) & GDPR Alignment (Data Minimization & Zero Retention)",
        "calm_control_requirement": {
            "control-id": "calm-finos-reg-01",
            "control-type": "contractual-zdr-and-no-training-enforcement",
            "enforcement": "zero-data-retention-and-no-model-training",
        },
    },
    {
        "risk_id": "FINOS-REG-02",
        "category_group": FinosRiskCategoryGroup.regulatory_compliance.value,
        "risk_name": "Regulatory oversight gaps",
        "description": (
            "Unreported changes to vendor model families, hosting geography, or agentic "
            "capabilities creating blind spots in SR 11-7 and EU AI Act model inventories."
        ),
        "default_severity": "HIGH",
        "sr_11_7_mapping": "SR 11-7 Section V.B (Comprehensive Enterprise Model Inventory)",
        "nist_ai_rmf_mapping": "GOVERN 1.4 / MAP 4.1 (Third-Party AI Inventory & Tracking)",
        "iso_42001_mapping": "ISO/IEC 42001 Annex A.4.2 (AI System Inventory & Documentation)",
        "eu_ai_act_mapping": "Article 11 & Annex IV (Technical Documentation & GPAI Disclosure)",
        "calm_control_requirement": {
            "control-id": "calm-finos-reg-02",
            "control-type": "continuous-vendor-snapshot-and-materiality-audit",
            "enforcement": "automated-model-inventory-synchronization",
        },
    },
    {
        "risk_id": "FINOS-REG-03",
        "category_group": FinosRiskCategoryGroup.regulatory_compliance.value,
        "risk_name": "Compliance failures",
        "description": (
            "Breach of sector-specific regulatory mandates (SR 11-7, EU AI Act Annex III, "
            "DORA, SEC/FINRA recordkeeping) due to unapproved vendor AI modifications."
        ),
        "default_severity": "CRITICAL",
        "sr_11_7_mapping": "SR 11-7 Section VI (Supervisory Examination Readiness & Signoff)",
        "nist_ai_rmf_mapping": "GOVERN 1.1 (Legal and Regulatory Requirement Compliance)",
        "iso_42001_mapping": "ISO/IEC 42001 Clause 6.1.3 (Compliance Obligations)",
        "eu_ai_act_mapping": "Article 16 & Annex III (High-Risk AI System Conformity)",
        "calm_control_requirement": {
            "control-id": "calm-finos-reg-03",
            "control-type": "immutable-governance-signoff-and-exam-pack-export",
            "enforcement": "cryptographic-owner-signoff-before-production-use",
        },
    },
]


def seed_finos_catalog(db: Session) -> list[FinosRiskControl]:
    """Ensure all 23 official FINOS AI Governance Framework v2 risk controls exist in PostgreSQL."""
    existing_ids = set(db.scalars(select(FinosRiskControl.risk_id)).all())
    for item in FINOS_V2_RISK_CATALOG:
        if item["risk_id"] not in existing_ids:
            db.add(
                FinosRiskControl(
                    risk_id=item["risk_id"],
                    category_group=FinosRiskCategoryGroup(item["category_group"]),
                    risk_name=item["risk_name"],
                    description=item["description"],
                    default_severity=item["default_severity"],
                    sr_11_7_mapping=item["sr_11_7_mapping"],
                    nist_ai_rmf_mapping=item["nist_ai_rmf_mapping"],
                    iso_42001_mapping=item["iso_42001_mapping"],
                    eu_ai_act_mapping=item["eu_ai_act_mapping"],
                    calm_control_requirement=item["calm_control_requirement"],
                )
            )
    db.commit()
    return list(
        db.scalars(select(FinosRiskControl).order_by(FinosRiskControl.risk_id)).all()
    )
