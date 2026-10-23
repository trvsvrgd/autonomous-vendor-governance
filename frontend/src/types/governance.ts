export type OnboardingStatus = "pending" | "active" | "under_review" | "restricted";
export type RiskTier = "critical" | "high" | "medium" | "low";
export type HostingTopology =
  | "vendor_hosted"
  | "aws_bedrock"
  | "vertex_ai"
  | "azure_openai"
  | "on_premise";
export type AutonomyClassification =
  | "deterministic"
  | "assistive_copilot"
  | "tool_calling_agent"
  | "multi_agent_autonomous";
export type SourceType =
  | "trust_center_url"
  | "release_notes_url"
  | "subprocessor_url"
  | "ula_contract_pdf"
  | "soc2_report"
  | "inbound_email_alias";
export type MaterialityLevel = "material" | "non_material" | "baseline";
export type ReviewStatus =
  | "awaiting_review"
  | "approved"
  | "rejected"
  | "mitigated"
  | "digest_sent";

export interface BusinessOwner {
  owner_id: string;
  external_idp_subject: string;
  full_name: string;
  email_address: string;
  department: string;
  notification_channel_preferences: {
    email_enabled?: boolean;
    slack_webhook_url?: string | null;
    teams_webhook_url?: string | null;
    jira_webhook_url?: string | null;
    digest_frequency?: string;
  };
  escalation_manager_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface VendorAICapability {
  capability_id: string;
  vendor_id: string;
  product_module_name: string;
  foundation_model_family: string;
  model_provider: string;
  hosting_topology: HostingTopology;
  autonomy_classification: AutonomyClassification;
  mcp_or_a2a_enabled: boolean;
  trains_on_customer_data: boolean;
  data_retention_days: number;
  active_snapshot_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestionSource {
  source_id: string;
  vendor_id: string;
  source_type: SourceType;
  target_uri_or_s3_key: string;
  polling_cron_schedule: string;
  last_polled_at: string | null;
  last_http_etag: string | null;
  last_sha256_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface VendorSnapshot {
  snapshot_id: string;
  source_id: string;
  vendor_id: string;
  raw_extracted_text: string;
  content_sha256_hash: string;
  s3_archive_uri: string;
  captured_at: string;
}

export interface MaterialityAssessment {
  assessment_id: string;
  vendor_id: string;
  previous_snapshot_id: string | null;
  new_snapshot_id: string;
  materiality_level: MaterialityLevel;
  executive_summary: string;
  detected_model_changes: Record<string, unknown>;
  detected_agentic_changes: Record<string, unknown>;
  impacted_finos_risk_ids: string[];
  recommended_actions: string;
  gemini_model_identifier: string;
  evaluated_at: string;
}

export interface GovernanceSignoff {
  signoff_id: string;
  assessment_id: string;
  vendor_id: string;
  assigned_owner_id: string;
  review_status: ReviewStatus;
  owner_decision_notes: string | null;
  cryptographic_signature_hash: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FinosRiskControl {
  risk_id: string;
  category_group: "operational" | "security" | "regulatory_compliance";
  risk_name: string;
  description: string;
  default_severity: string;
  sr_11_7_mapping: string;
  nist_ai_rmf_mapping: string;
  iso_42001_mapping: string;
  eu_ai_act_mapping: string;
  calm_control_requirement: Record<string, unknown>;
}

export interface VendorSummaryRow {
  vendor_id: string;
  legal_name: string;
  primary_domain: string;
  onboarding_status: OnboardingStatus;
  risk_tier: RiskTier;
  primary_owner: BusinessOwner;
  secondary_owner: BusinessOwner | null;
  ai_capabilities: VendorAICapability[];
  active_material_alerts_count: number;
  latest_review_status: ReviewStatus | null;
  latest_assessment_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CommandCenterKPIs {
  total_vendors_monitored: number;
  active_material_alerts_awaiting_signoff: number;
  autonomous_agent_vendor_percentage: number;
  critical_or_high_risk_vendors: number;
  total_snapshots_archived: number;
}

export interface CommandCenterResponse {
  kpis: CommandCenterKPIs;
  vendors: VendorSummaryRow[];
  total_count: number;
}

export interface TriageQueueItem {
  signoff: GovernanceSignoff;
  assessment: MaterialityAssessment;
  vendor_id: string;
  vendor_legal_name: string;
  vendor_primary_domain: string;
  vendor_risk_tier: RiskTier;
  assigned_owner: BusinessOwner;
  previous_snapshot_text: string;
  new_snapshot_text: string;
  previous_snapshot_captured_at: string | null;
  new_snapshot_captured_at: string;
  source_type: SourceType;
  source_uri: string;
  triggered_finos_controls: FinosRiskControl[];
}

export interface VendorDetailResponse {
  vendor: VendorSummaryRow;
  ingestion_sources: IngestionSource[];
  snapshots: VendorSnapshot[];
  assessments: MaterialityAssessment[];
  signoffs: GovernanceSignoff[];
}

export interface DigestOwnerGroup {
  owner_id: string;
  owner_full_name: string;
  owner_email: string;
  department: string;
  notification_channel_preferences: Record<string, unknown>;
  window_hours: number;
  items: {
    signoff_id: string;
    assessment_id: string;
    vendor_id: string;
    vendor_legal_name: string;
    vendor_primary_domain: string;
    executive_summary: string;
    evaluated_at: string;
    review_status: ReviewStatus;
  }[];
}
