import {
  BusinessOwner,
  CommandCenterResponse,
  DigestOwnerGroup,
  FinosRiskControl,
  GovernanceSignoff,
  IngestionSource,
  SourceType,
  TriageQueueItem,
  VendorDetailResponse,
  VendorSummaryRow,
} from "../types/governance";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    let errText = response.statusText;
    try {
      const errJson = await response.json();
      errText = errJson.detail || JSON.stringify(errJson);
    } catch {
      errText = await response.text();
    }
    throw new Error(errText || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const governanceApi = {
  getHealth(): Promise<{
    status: string;
    gemini_execution_mode: string;
    gemini_model_id: string;
    finos_v2_controls_seeded: number;
    vendors_monitored: number;
  }> {
    return requestJson("/health");
  },

  listOwners(): Promise<BusinessOwner[]> {
    return requestJson(`${API_BASE}/owners`);
  },

  createOwner(payload: {
    external_idp_subject: string;
    full_name: string;
    email_address: string;
    department: string;
    notification_channel_preferences: Record<string, unknown>;
    escalation_manager_id?: string | null;
  }): Promise<BusinessOwner> {
    return requestJson(`${API_BASE}/owners`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listVendors(params: {
    risk_tier?: string;
    owner_id?: string;
    foundation_model_family?: string;
    autonomy_classification?: string;
    review_status?: string;
    search?: string;
  }): Promise<CommandCenterResponse> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) query.set(k, v);
    });
    const qs = query.toString();
    return requestJson(`${API_BASE}/vendors${qs ? `?${qs}` : ""}`);
  },

  onboardVendor(payload: Record<string, unknown>): Promise<VendorSummaryRow> {
    return requestJson(`${API_BASE}/vendors`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  bulkOnboardCsv(file: File): Promise<{
    status: string;
    created_vendors: number;
    updated_vendors: number;
    baseline_assessments_created: number;
  }> {
    const formData = new FormData();
    formData.append("file", file);
    return requestJson(`${API_BASE}/vendors/bulk-csv`, {
      method: "POST",
      body: formData,
    });
  },

  getVendorDetail(vendorId: string): Promise<VendorDetailResponse> {
    return requestJson(`${API_BASE}/vendors/${vendorId}`);
  },

  addIngestionSource(
    vendorId: string,
    payload: {
      source_type: SourceType;
      target_uri_or_s3_key: string;
      polling_cron_schedule: string;
    }
  ): Promise<IngestionSource> {
    return requestJson(`${API_BASE}/vendors/${vendorId}/sources`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  forceCrawlAndEvaluate(
    vendorId: string,
    payload: { source_id?: string; override_snapshot_text?: string }
  ): Promise<Record<string, unknown>> {
    return requestJson(`${API_BASE}/vendors/${vendorId}/crawl-and-evaluate`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  uploadVendorDocument(
    vendorId: string,
    sourceType: SourceType,
    file: File
  ): Promise<Record<string, unknown>> {
    const formData = new FormData();
    formData.append("source_type", sourceType);
    formData.append("file", file);
    return requestJson(`${API_BASE}/ingestion/vendors/${vendorId}/documents`, {
      method: "POST",
      body: formData,
    });
  },

  sendInboundVendorWebhook(payload: {
    sender_email_or_domain: string;
    subject: string;
    body_text: string;
  }): Promise<Record<string, unknown>> {
    return requestJson(`${API_BASE}/ingestion/webhooks/vendor-bulletin`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listTriageQueue(params?: {
    materiality_level?: string;
    review_status?: string;
    vendor_id?: string;
  }): Promise<TriageQueueItem[]> {
    const query = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v) query.set(k, v);
      });
    }
    const qs = query.toString();
    return requestJson(`${API_BASE}/triage${qs ? `?${qs}` : ""}`);
  },

  submitSignoffDecision(
    signoffId: string,
    payload: {
      action: "approve" | "require_remediation" | "escalate_to_legal";
      owner_decision_notes: string;
      actor_owner_id?: string;
    }
  ): Promise<GovernanceSignoff> {
    return requestJson(`${API_BASE}/triage/${signoffId}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getFinosCatalog(): Promise<FinosRiskControl[]> {
    return requestJson(`${API_BASE}/reports/finos-catalog`);
  },

  previewDigests(windowHours: number): Promise<DigestOwnerGroup[]> {
    return requestJson(`${API_BASE}/reports/digests/preview?window_hours=${windowHours}`);
  },

  dispatchDigests(windowHours: number): Promise<{
    dispatched_at: string;
    window_hours: number;
    owners_notified: number;
    total_assessments_digested: number;
  }> {
    return requestJson(`${API_BASE}/reports/digests/dispatch?window_hours=${windowHours}`, {
      method: "POST",
    });
  },

  getRegulatoryJsonExport(
    framework: "sr_11_7" | "nist_iso_42001" | "eu_ai_act" | "finos_calm" | "unified_pack",
    vendorId?: string
  ): Promise<Record<string, unknown>> {
    const query = new URLSearchParams({ framework });
    if (vendorId) query.set("vendor_id", vendorId);
    return requestJson(`${API_BASE}/reports/export/json?${query.toString()}`);
  },

  getRegulatoryPdfDownloadUrl(
    framework: "sr_11_7" | "nist_iso_42001" | "eu_ai_act" | "finos_calm" | "unified_pack",
    vendorId?: string
  ): string {
    const query = new URLSearchParams({ framework });
    if (vendorId) query.set("vendor_id", vendorId);
    return `${API_BASE}/reports/export/pdf?${query.toString()}`;
  },
};
