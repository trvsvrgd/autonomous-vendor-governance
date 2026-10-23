import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Building2,
  Database,
  Filter,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Upload,
  UserPlus,
} from "lucide-react";
import { governanceApi } from "../api/client";
import {
  AutonomyClassification,
  BusinessOwner,
  CommandCenterResponse,
  HostingTopology,
  ReviewStatus,
  RiskTier,
  SourceType,
} from "../types/governance";

interface CommandCenterProps {
  onSelectVendor: (vendorId: string) => void;
  onNavigateTriage: () => void;
}

export const CommandCenter: React.FC<CommandCenterProps> = ({
  onSelectVendor,
  onNavigateTriage,
}) => {
  const [data, setData] = useState<CommandCenterResponse | null>(null);
  const [owners, setOwners] = useState<BusinessOwner[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Server-side filters
  const [riskTier, setRiskTier] = useState<string>("");
  const [ownerId, setOwnerId] = useState<string>("");
  const [modelFamily, setModelFamily] = useState<string>("");
  const [autonomy, setAutonomy] = useState<string>("");
  const [reviewStatus, setReviewStatus] = useState<string>("");
  const [search, setSearch] = useState<string>("");

  // Modals
  const [showOnboardModal, setShowOnboardModal] = useState<boolean>(false);
  const [showOwnerModal, setShowOwnerModal] = useState<boolean>(false);
  const [csvUploading, setCsvUploading] = useState<boolean>(false);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  // Single vendor form state
  const [legalName, setLegalName] = useState("");
  const [primaryDomain, setPrimaryDomain] = useState("");
  const [newRiskTier, setNewRiskTier] = useState<RiskTier>("critical");
  const [selectedOwnerId, setSelectedOwnerId] = useState("");
  const [moduleName, setModuleName] = useState("");
  const [foundationModel, setFoundationModel] = useState("Claude 3.7 Sonnet");
  const [modelProvider, setModelProvider] = useState("Anthropic");
  const [hostingTopology, setHostingTopology] =
    useState<HostingTopology>("aws_bedrock");
  const [autonomyClass, setAutonomyClass] =
    useState<AutonomyClassification>("tool_calling_agent");
  const [mcpEnabled, setMcpEnabled] = useState(false);
  const [trainsOnData, setTrainsOnData] = useState(false);
  const [retentionDays, setRetentionDays] = useState(0);
  const [sourceType, setSourceType] = useState<SourceType>("trust_center_url");
  const [sourceUri, setSourceUri] = useState("");

  // Owner creation state
  const [ownerFullName, setOwnerFullName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerDept, setOwnerDept] = useState("Enterprise AI Governance");
  const [ownerIdpSub, setOwnerIdpSub] = useState("");
  const [ownerSlackWebhook, setOwnerSlackWebhook] = useState("");

  const fetchCommandCenter = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ccResp, ownersResp] = await Promise.all([
        governanceApi.listVendors({
          risk_tier: riskTier || undefined,
          owner_id: ownerId || undefined,
          foundation_model_family: modelFamily || undefined,
          autonomy_classification: autonomy || undefined,
          review_status: reviewStatus || undefined,
          search: search || undefined,
        }),
        governanceApi.listOwners(),
      ]);
      setData(ccResp);
      setOwners(ownersResp);
      if (!selectedOwnerId && ownersResp.length > 0) {
        setSelectedOwnerId(ownersResp[0].owner_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchCommandCenter();
  }, [riskTier, ownerId, modelFamily, autonomy, reviewStatus]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void fetchCommandCenter();
  };

  const handleCreateOwner = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await governanceApi.createOwner({
        external_idp_subject: ownerIdpSub || `oidc:${ownerEmail}`,
        full_name: ownerFullName,
        email_address: ownerEmail,
        department: ownerDept,
        notification_channel_preferences: {
          email_enabled: true,
          slack_webhook_url: ownerSlackWebhook || null,
          digest_frequency: "24h",
        },
      });
      setShowOwnerModal(false);
      setOwnerFullName("");
      setOwnerEmail("");
      setOwnerIdpSub("");
      setSelectedOwnerId(created.owner_id);
      setStatusBanner(`Registered Business Owner: ${created.full_name}`);
      await fetchCommandCenter();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleOnboardVendor = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await governanceApi.onboardVendor({
        legal_name: legalName,
        primary_domain: primaryDomain,
        onboarding_status: "active",
        risk_tier: newRiskTier,
        primary_owner_id: selectedOwnerId,
        ai_capabilities: [
          {
            product_module_name: moduleName || `${legalName} AI Platform`,
            foundation_model_family: foundationModel,
            model_provider: modelProvider,
            hosting_topology: hostingTopology,
            autonomy_classification: autonomyClass,
            mcp_or_a2a_enabled: mcpEnabled,
            trains_on_customer_data: trainsOnData,
            data_retention_days: retentionDays,
          },
        ],
        ingestion_sources: sourceUri
          ? [
              {
                source_type: sourceType,
                target_uri_or_s3_key: sourceUri,
                polling_cron_schedule: "0 */6 * * *",
              },
            ]
          : [],
        trigger_immediate_baseline: true,
      });
      setShowOnboardModal(false);
      setLegalName("");
      setPrimaryDomain("");
      setModuleName("");
      setSourceUri("");
      setStatusBanner(
        `Onboarded ${created.legal_name} (${created.primary_domain}) and scheduled EventBridge baseline collection.`
      );
      await fetchCommandCenter();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleBulkCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvUploading(true);
    setError(null);
    try {
      const res = await governanceApi.bulkOnboardCsv(file);
      setStatusBanner(
        `Bulk CSV Intake complete: ${res.created_vendors} created, ${res.updated_vendors} updated, ${res.baseline_assessments_created} baseline Gemini evaluations recorded.`
      );
      await fetchCommandCenter();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCsvUploading(false);
      e.target.value = "";
    }
  };

  const kpis = data?.kpis;

  return (
    <div className="space-y-6">
      {/* Top Action Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-400">
            <span>AWS Agentic Value Accelerator v5.0 Govern</span>
            <span>•</span>
            <span>FINOS AI Governance v2</span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">
            Enterprise Vendor Command Center
          </h1>
          <p className="text-sm text-slate-400">
            Real-time single source of truth across third-party AI vendors, foundation model lineages, and autonomous agent capabilities.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setShowOwnerModal(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <UserPlus className="h-4 w-4 text-blue-400" />
            Add Business Owner
          </button>

          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800">
            <Upload className="h-4 w-4 text-emerald-400" />
            <span>{csvUploading ? "Importing CSV..." : "Bulk CSV Intake"}</span>
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleBulkCsvUpload}
              disabled={csvUploading}
            />
          </label>

          <button
            onClick={() => setShowOnboardModal(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-blue-500"
          >
            <Plus className="h-4 w-4" />
            Onboard AI Vendor
          </button>

          <button
            onClick={() => void fetchCommandCenter()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 p-2 text-slate-300 hover:bg-slate-800"
            title="Refresh live PostgreSQL state"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {statusBanner && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-200 flex items-center justify-between">
          <span>{statusBanner}</span>
          <button
            onClick={() => setStatusBanner(null)}
            className="text-xs underline ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Total Vendors Monitored</span>
            <Building2 className="h-4 w-4 text-blue-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-white">
            {kpis ? kpis.total_vendors_monitored : "—"}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Active PostgreSQL inventory
          </div>
        </div>

        <div
          onClick={onNavigateTriage}
          className="cursor-pointer rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 hover:border-rose-500/60 transition"
        >
          <div className="flex items-center justify-between text-rose-300 text-xs font-medium">
            <span>Material Alerts Awaiting Sign-Off</span>
            <AlertTriangle className="h-4 w-4 text-rose-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-rose-400">
            {kpis ? kpis.active_material_alerts_awaiting_signoff : "—"}
          </div>
          <div className="mt-1 text-xs text-rose-300/80">
            Click to open Triage & Signoff Queue →
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Autonomous / Agentic Vendors</span>
            <Bot className="h-4 w-4 text-purple-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-purple-300">
            {kpis ? `${kpis.autonomous_agent_vendor_percentage}%` : "—"}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Tool-calling, Multi-Agent, or MCP/A2A
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Critical / High Risk Tier</span>
            <ShieldAlert className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-amber-300">
            {kpis ? kpis.critical_or_high_risk_vendors : "—"}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            SR 11-7 & EU AI Act Annex III scope
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Encrypted S3 Snapshots</span>
            <Database className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-emerald-300">
            {kpis ? kpis.total_snapshots_archived : "—"}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            SHA-256 verified immutable archives
          </div>
        </div>
      </div>

      {/* Server-Side Filter Bar */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          <Filter className="h-3.5 w-3.5 text-blue-400" />
          <span>Instant Server-Side Inventory Filtering</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
          <form onSubmit={handleSearchSubmit} className="relative">
            <Search className="h-4 w-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search vendor, domain, model..."
              className="w-full rounded-lg border border-slate-700 bg-slate-950 pl-9 pr-3 py-1.5 text-xs text-slate-100 focus:border-blue-500 focus:outline-none"
            />
          </form>

          <select
            value={riskTier}
            onChange={(e) => setRiskTier(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Risk Tiers</option>
            <option value="critical">Critical Tier</option>
            <option value="high">High Tier</option>
            <option value="medium">Medium Tier</option>
            <option value="low">Low Tier</option>
          </select>

          <select
            value={ownerId}
            onChange={(e) => setOwnerId(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Business Owners</option>
            {owners.map((o) => (
              <option key={o.owner_id} value={o.owner_id}>
                {o.full_name} ({o.department})
              </option>
            ))}
          </select>

          <input
            type="text"
            value={modelFamily}
            onChange={(e) => setModelFamily(e.target.value)}
            placeholder="Filter Model Family (e.g. Claude, GPT)"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
          />

          <select
            value={autonomy}
            onChange={(e) => setAutonomy(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Autonomy Classifications</option>
            <option value="deterministic">Deterministic</option>
            <option value="assistive_copilot">Assistive Copilot</option>
            <option value="tool_calling_agent">Tool-Calling Agent</option>
            <option value="multi_agent_autonomous">Multi-Agent Autonomous</option>
          </select>

          <select
            value={reviewStatus}
            onChange={(e) => setReviewStatus(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Signoff Statuses</option>
            <option value="awaiting_review">Awaiting Review</option>
            <option value="approved">Approved</option>
            <option value="mitigated">Mitigated / Remediation</option>
            <option value="rejected">Rejected / Restricted</option>
            <option value="digest_sent">Digest Sent</option>
          </select>
        </div>
      </div>

      {/* High-Density Enterprise Data Grid */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                <th className="py-3 px-4">Vendor & Domain</th>
                <th className="py-3 px-3">Status & Risk Tier</th>
                <th className="py-3 px-3">Foundation Model & Hosting</th>
                <th className="py-3 px-3">Agentic Autonomy & Data Rights</th>
                <th className="py-3 px-3">Accountable Owner</th>
                <th className="py-3 px-3">Governance Signoff</th>
                <th className="py-3 px-4 text-right">Workspace</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 text-xs">
              {data?.vendors.map((v) => {
                const primaryCap = v.ai_capabilities[0];
                return (
                  <tr
                    key={v.vendor_id}
                    className="hover:bg-slate-800/40 transition cursor-pointer"
                    onClick={() => onSelectVendor(v.vendor_id)}
                  >
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-white">{v.legal_name}</div>
                      <div className="text-slate-400 font-mono text-[11px]">
                        {v.primary_domain}
                      </div>
                    </td>

                    <td className="py-3.5 px-3">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                            v.risk_tier === "critical"
                              ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                              : v.risk_tier === "high"
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                              : v.risk_tier === "medium"
                              ? "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                              : "bg-slate-700 text-slate-300"
                          }`}
                        >
                          {v.risk_tier}
                        </span>
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-medium ${
                            v.onboarding_status === "active"
                              ? "bg-emerald-500/15 text-emerald-300"
                              : v.onboarding_status === "under_review"
                              ? "bg-amber-500/15 text-amber-300"
                              : v.onboarding_status === "restricted"
                              ? "bg-rose-500/20 text-rose-300"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {v.onboarding_status.replace("_", " ")}
                        </span>
                      </div>
                    </td>

                    <td className="py-3.5 px-3">
                      {primaryCap ? (
                        <div>
                          <div className="font-medium text-slate-100">
                            {primaryCap.foundation_model_family}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {primaryCap.model_provider} •{" "}
                            <span className="font-mono">
                              {primaryCap.hosting_topology}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-500">No capability mapped</span>
                      )}
                    </td>

                    <td className="py-3.5 px-3">
                      {primaryCap ? (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5">
                            <span className="rounded bg-purple-500/20 border border-purple-500/30 px-2 py-0.5 text-[10px] font-semibold text-purple-300">
                              {primaryCap.autonomy_classification}
                            </span>
                            {primaryCap.mcp_or_a2a_enabled && (
                              <span className="rounded bg-indigo-500/25 border border-indigo-400/40 px-1.5 py-0.5 text-[10px] font-bold text-indigo-200">
                                MCP/A2A
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {primaryCap.trains_on_customer_data ? (
                              <span className="text-rose-400 font-semibold">
                                Trains on Customer Data ({primaryCap.data_retention_days}d retention)
                              </span>
                            ) : (
                              <span className="text-emerald-400">
                                Zero Training • {primaryCap.data_retention_days}d retention
                              </span>
                            )}
                          </div>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>

                    <td className="py-3.5 px-3">
                      <div className="font-medium text-slate-200">
                        {v.primary_owner.full_name}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        {v.primary_owner.department}
                      </div>
                    </td>

                    <td className="py-3.5 px-3">
                      <div className="flex flex-col gap-1">
                        {v.active_material_alerts_count > 0 && (
                          <span className="inline-flex items-center gap-1 rounded bg-rose-500/20 border border-rose-500/40 px-2 py-0.5 text-[10px] font-bold text-rose-300 w-fit">
                            <AlertTriangle className="h-3 w-3" />
                            {v.active_material_alerts_count} Material Alert
                          </span>
                        )}
                        <span className="text-[11px] text-slate-300">
                          Status:{" "}
                          <span className="font-mono text-slate-200">
                            {v.latest_review_status || "baseline"}
                          </span>
                        </span>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectVendor(v.vendor_id);
                        }}
                        className="rounded-lg border border-blue-500/40 bg-blue-950/40 px-3 py-1 text-xs font-medium text-blue-300 hover:bg-blue-900/50"
                      >
                        Inspect & Crawl →
                      </button>
                    </td>
                  </tr>
                );
              })}

              {!loading && data?.vendors.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    No vendors match the current filters. Use "Onboard AI Vendor" or "Bulk CSV Intake" to register vendors.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Create Business Owner */}
      {showOwnerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-white">
              Register Corporate Business Owner
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Binds corporate OIDC / AWS Cognito identity to vendor accountability and signoff routing.
            </p>
            <form onSubmit={handleCreateOwner} className="mt-4 space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 mb-1">Full Name</label>
                <input
                  required
                  value={ownerFullName}
                  onChange={(e) => setOwnerFullName(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  placeholder="Elena Rostova"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1">Corporate Email</label>
                <input
                  required
                  type="email"
                  value={ownerEmail}
                  onChange={(e) => setOwnerEmail(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  placeholder="elena.rostova@enterprise.com"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1">Department</label>
                <input
                  required
                  value={ownerDept}
                  onChange={(e) => setOwnerDept(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1">
                  External OIDC Subject (sub)
                </label>
                <input
                  value={ownerIdpSub}
                  onChange={(e) => setOwnerIdpSub(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  placeholder="oidc:cognito:elena.rostova"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1">
                  Slack Webhook URL (Optional)
                </label>
                <input
                  value={ownerSlackWebhook}
                  onChange={(e) => setOwnerSlackWebhook(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  placeholder="https://hooks.slack.com/services/..."
                />
              </div>
              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowOwnerModal(false)}
                  className="rounded border border-slate-700 px-4 py-2 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-500"
                >
                  Save Business Owner
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Onboard Single Vendor */}
      {showOnboardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 overflow-y-auto">
          <div className="w-full max-w-2xl rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl my-8">
            <h2 className="text-lg font-bold text-white">
              Onboard New Third-Party AI Vendor
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Creates transactional vendor + capability records and schedules immediate AWS EventBridge / SQS baseline collection.
            </p>
            <form onSubmit={handleOnboardVendor} className="mt-4 space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 mb-1">Vendor Legal Name</label>
                  <input
                    required
                    value={legalName}
                    onChange={(e) => setLegalName(e.target.value)}
                    placeholder="Anthropic PBC"
                    className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">Primary Domain</label>
                  <input
                    required
                    value={primaryDomain}
                    onChange={(e) => setPrimaryDomain(e.target.value)}
                    placeholder="anthropic.com"
                    className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">Risk Tier</label>
                  <select
                    value={newRiskTier}
                    onChange={(e) => setNewRiskTier(e.target.value as RiskTier)}
                    className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">
                    Accountable Business Owner
                  </label>
                  <select
                    required
                    value={selectedOwnerId}
                    onChange={(e) => setSelectedOwnerId(e.target.value)}
                    className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  >
                    {owners.map((o) => (
                      <option key={o.owner_id} value={o.owner_id}>
                        {o.full_name} ({o.department})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="border-t border-slate-800 pt-3">
                <div className="font-semibold text-slate-200 mb-2">
                  Initial AI Capability & Model Lineage
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-slate-300 mb-1">Product Module</label>
                    <input
                      required
                      value={moduleName}
                      onChange={(e) => setModuleName(e.target.value)}
                      placeholder="Claude Enterprise Agent"
                      className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-300 mb-1">
                      Foundation Model Family
                    </label>
                    <input
                      required
                      value={foundationModel}
                      onChange={(e) => setFoundationModel(e.target.value)}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-300 mb-1">Model Provider</label>
                    <input
                      required
                      value={modelProvider}
                      onChange={(e) => setModelProvider(e.target.value)}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-300 mb-1">Hosting Topology</label>
                    <select
                      value={hostingTopology}
                      onChange={(e) =>
                        setHostingTopology(e.target.value as HostingTopology)
                      }
                      className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                    >
                      <option value="vendor_hosted">Vendor Hosted</option>
                      <option value="aws_bedrock">AWS Bedrock</option>
                      <option value="vertex_ai">Google Cloud Vertex AI</option>
                      <option value="azure_openai">Azure OpenAI</option>
                      <option value="on_premise">On-Premise</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-300 mb-1">
                      Autonomy Classification
                    </label>
                    <select
                      value={autonomyClass}
                      onChange={(e) =>
                        setAutonomyClass(e.target.value as AutonomyClassification)
                      }
                      className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                    >
                      <option value="deterministic">Deterministic</option>
                      <option value="assistive_copilot">Assistive Copilot</option>
                      <option value="tool_calling_agent">Tool-Calling Agent</option>
                      <option value="multi_agent_autonomous">
                        Multi-Agent Autonomous
                      </option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-300 mb-1">
                      Data Retention (Days)
                    </label>
                    <input
                      type="number"
                      min={0}
                      value={retentionDays}
                      onChange={(e) => setRetentionDays(Number(e.target.value))}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-6 mt-3">
                  <label className="inline-flex items-center gap-2 text-slate-300">
                    <input
                      type="checkbox"
                      checked={mcpEnabled}
                      onChange={(e) => setMcpEnabled(e.target.checked)}
                    />
                    <span>MCP Server or A2A Protocol Enabled</span>
                  </label>
                  <label className="inline-flex items-center gap-2 text-slate-300">
                    <input
                      type="checkbox"
                      checked={trainsOnData}
                      onChange={(e) => setTrainsOnData(e.target.checked)}
                    />
                    <span>Trains on Customer Data</span>
                  </label>
                </div>
              </div>

              <div className="border-t border-slate-800 pt-3">
                <div className="font-semibold text-slate-200 mb-2">
                  Primary Monitored Ingestion URL (Optional)
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <select
                    value={sourceType}
                    onChange={(e) => setSourceType(e.target.value as SourceType)}
                    className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  >
                    <option value="trust_center_url">Trust Center URL</option>
                    <option value="release_notes_url">Release Notes URL</option>
                    <option value="subprocessor_url">Subprocessor List URL</option>
                  </select>
                  <input
                    value={sourceUri}
                    onChange={(e) => setSourceUri(e.target.value)}
                    placeholder="https://example.com/security/trust"
                    className="sm:col-span-2 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowOnboardModal(false)}
                  className="rounded border border-slate-700 px-4 py-2 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded bg-blue-600 px-5 py-2 font-semibold text-white hover:bg-blue-500"
                >
                  Onboard & Schedule Baseline
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
