import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  Cpu,
  FileUp,
  Globe,
  History,
  Play,
  Plus,
  Radio,
  ShieldCheck,
} from "lucide-react";
import { governanceApi } from "../api/client";
import { SourceType, VendorDetailResponse } from "../types/governance";

interface VendorDetailProps {
  vendorId: string;
  onBack: () => void;
  onOpenTriage: () => void;
}

export const VendorDetail: React.FC<VendorDetailProps> = ({
  vendorId,
  onBack,
  onOpenTriage,
}) => {
  const [detail, setDetail] = useState<VendorDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [crawling, setCrawling] = useState<boolean>(false);
  const [uploadingDoc, setUploadingDoc] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Add source state
  const [newSourceType, setNewSourceType] =
    useState<SourceType>("release_notes_url");
  const [newSourceUri, setNewSourceUri] = useState<string>("");
  const [newSourceCron, setNewSourceCron] = useState<string>("0 */6 * * *");

  // Live crawl / snapshot evaluation state
  const [selectedSourceId, setSelectedSourceId] = useState<string>("");
  const [overrideSnapshotText, setOverrideSnapshotText] = useState<string>("");

  // Document upload type
  const [docSourceType, setDocSourceType] =
    useState<SourceType>("ula_contract_pdf");

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await governanceApi.getVendorDetail(vendorId);
      setDetail(res);
      if (!selectedSourceId && res.ingestion_sources.length > 0) {
        setSelectedSourceId(res.ingestion_sources[0].source_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, [vendorId]);

  const handleAddSource = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await governanceApi.addIngestionSource(vendorId, {
        source_type: newSourceType,
        target_uri_or_s3_key: newSourceUri,
        polling_cron_schedule: newSourceCron,
      });
      setNewSourceUri("");
      setStatusMsg("Added monitored ingestion source and registered EventBridge rule.");
      await loadDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleForceCrawlAndEvaluate = async () => {
    setCrawling(true);
    setError(null);
    setStatusMsg(null);
    try {
      const res = await governanceApi.forceCrawlAndEvaluate(vendorId, {
        source_id: selectedSourceId || undefined,
        override_snapshot_text: overrideSnapshotText.trim() || undefined,
      });
      const assessment = res.assessment as Record<string, unknown> | undefined;
      setStatusMsg(
        assessment
          ? `Live Crawl & Gemini Evaluation completed: Materiality = ${String(
              assessment.materiality_level
            ).toUpperCase()}`
          : "Live crawl finished (SHA-256 unchanged)."
      );
      setOverrideSnapshotText("");
      await loadDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCrawling(false);
    }
  };

  const handleUploadContractDocument = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingDoc(true);
    setError(null);
    try {
      const res = await governanceApi.uploadVendorDocument(
        vendorId,
        docSourceType,
        file
      );
      const assessment = res.assessment as Record<string, unknown>;
      setStatusMsg(
        `Archived '${file.name}' to encrypted S3 and executed Gemini evaluation: ${String(
          assessment.materiality_level
        ).toUpperCase()}`
      );
      await loadDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploadingDoc(false);
      e.target.value = "";
    }
  };

  if (loading && !detail) {
    return (
      <div className="p-12 text-center text-sm text-slate-400">
        Loading vendor governance workspace...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-12 text-center text-sm text-rose-400">
        Vendor record not found.
      </div>
    );
  }

  const { vendor, ingestion_sources, snapshots, assessments, signoffs } = detail;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-lg border border-slate-700 bg-slate-900 p-2 text-slate-300 hover:bg-slate-800"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-bold text-white">{vendor.legal_name}</h1>
              <span className="rounded bg-blue-500/20 border border-blue-500/40 px-2 py-0.5 text-xs font-mono text-blue-300">
                {vendor.primary_domain}
              </span>
              <span className="rounded bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-xs font-bold uppercase text-amber-300">
                {vendor.risk_tier} risk
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Primary Owner: <b className="text-slate-200">{vendor.primary_owner.full_name}</b> (
              {vendor.primary_owner.email_address}) • Onboarding Status:{" "}
              <b className="text-slate-200">{vendor.onboarding_status}</b>
            </p>
          </div>
        </div>

        <button
          onClick={onOpenTriage}
          className="rounded-lg bg-rose-600/90 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500"
        >
          Open Signoff Queue ({vendor.active_material_alerts_count} Active Alerts)
        </button>
      </div>

      {statusMsg && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-xs text-emerald-200">
          {statusMsg}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-xs text-rose-200">
          {error}
        </div>
      )}

      {/* AI Capabilities Inventory */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-400 mb-3">
          <Cpu className="h-4 w-4" />
          <span>Active AI Capabilities & Foundation Model Lineage</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {vendor.ai_capabilities.map((cap) => (
            <div
              key={cap.capability_id}
              className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-xs space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-white">
                  {cap.product_module_name}
                </span>
                <span className="rounded bg-purple-500/20 border border-purple-500/40 px-2 py-0.5 text-[10px] font-bold text-purple-300">
                  {cap.autonomy_classification}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-slate-300 pt-1">
                <div>
                  <span className="text-slate-500">Foundation Model:</span>{" "}
                  <b>{cap.foundation_model_family}</b>
                </div>
                <div>
                  <span className="text-slate-500">Provider:</span>{" "}
                  <b>{cap.model_provider}</b>
                </div>
                <div>
                  <span className="text-slate-500">Hosting Topology:</span>{" "}
                  <span className="font-mono">{cap.hosting_topology}</span>
                </div>
                <div>
                  <span className="text-slate-500">MCP / A2A Enabled:</span>{" "}
                  <b>{cap.mcp_or_a2a_enabled ? "YES" : "NO"}</b>
                </div>
                <div>
                  <span className="text-slate-500">Trains on Customer Data:</span>{" "}
                  <b className={cap.trains_on_customer_data ? "text-rose-400" : "text-emerald-400"}>
                    {cap.trains_on_customer_data ? "YES" : "NO (ZDR)"}
                  </b>
                </div>
                <div>
                  <span className="text-slate-500">Data Retention:</span>{" "}
                  <b>{cap.data_retention_days} days</b>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Crawl / Gemini Evaluation Trigger + Contract/ULA Upload */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-4">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
            <Radio className="h-4 w-4" />
            <span>Force Immediate Live Crawl & Gemini Harness Evaluation</span>
          </div>
          <p className="text-xs text-slate-400">
            Executes SSRF-protected <code className="text-slate-200">safe_fetch</code> against the selected vendor URL (or evaluates a live policy update text payload), archives to encrypted S3, and runs <code className="text-slate-200">GeminiGovernanceEvaluator.evaluateVendorDiff()</code>.
          </p>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-300 mb-1">Target Monitored Source</label>
              <select
                value={selectedSourceId}
                onChange={(e) => setSelectedSourceId(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
              >
                {ingestion_sources.map((s) => (
                  <option key={s.source_id} value={s.source_id}>
                    [{s.source_type}] {s.target_uri_or_s3_key}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-slate-300 mb-1">
                Optional Live Policy / Release Notes Payload Override (Leave blank to perform live HTTP safe_fetch)
              </label>
              <textarea
                rows={4}
                value={overrideSnapshotText}
                onChange={(e) => setOverrideSnapshotText(e.target.value)}
                placeholder="Paste updated vendor Trust Center disclosure, Subprocessor update, or ULA addendum text here to evaluate its materiality against the prior snapshot..."
                className="w-full rounded border border-slate-700 bg-slate-950 p-2.5 text-white font-mono text-[11px]"
              />
            </div>

            <button
              onClick={handleForceCrawlAndEvaluate}
              disabled={crawling}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {crawling
                ? "Running Live Crawl & Gemini Evaluation..."
                : "Force Live Crawl & Gemini Evaluation"}
            </button>
          </div>
        </div>

        {/* ULA / SOC 2 PDF & DOCX Ingestion + Source Configuration */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-5">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-purple-400 mb-2">
              <FileUp className="h-4 w-4" />
              <span>Contract, ULA & SOC 2 Document Ingestion (S3 + SQS)</span>
            </div>
            <p className="text-xs text-slate-400 mb-3">
              Upload a PDF or DOCX enterprise ULA, AI Addendum, or SOC 2 Type II report to extract text/tabular disclosures, archive to encrypted S3, and evaluate via Gemini.
            </p>
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <select
                value={docSourceType}
                onChange={(e) => setDocSourceType(e.target.value as SourceType)}
                className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
              >
                <option value="ula_contract_pdf">Enterprise ULA / AI Addendum (PDF/DOCX)</option>
                <option value="soc2_report">SOC 2 Report (PDF/DOCX)</option>
              </select>

              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 font-semibold text-white hover:bg-purple-500">
                <FileUp className="h-4 w-4" />
                <span>{uploadingDoc ? "Extracting & Evaluating..." : "Upload PDF / DOCX"}</span>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt"
                  className="hidden"
                  onChange={handleUploadContractDocument}
                  disabled={uploadingDoc}
                />
              </label>
            </div>
          </div>

          <form
            onSubmit={handleAddSource}
            className="border-t border-slate-800 pt-4 space-y-3 text-xs"
          >
            <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-slate-300">
              <Globe className="h-4 w-4 text-blue-400" />
              <span>Add Monitored URL or Inbound Alias</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <select
                value={newSourceType}
                onChange={(e) => setNewSourceType(e.target.value as SourceType)}
                className="rounded border border-slate-700 bg-slate-950 px-2.5 py-2 text-white"
              >
                <option value="trust_center_url">Trust Center URL</option>
                <option value="release_notes_url">Release Notes URL</option>
                <option value="subprocessor_url">Subprocessor List URL</option>
                <option value="inbound_email_alias">Inbound SES Email Alias</option>
              </select>
              <input
                required
                value={newSourceUri}
                onChange={(e) => setNewSourceUri(e.target.value)}
                placeholder="https://vendor.com/release-notes"
                className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
              />
              <div className="flex gap-2">
                <input
                  value={newSourceCron}
                  onChange={(e) => setNewSourceCron(e.target.value)}
                  placeholder="0 */6 * * *"
                  className="w-full rounded border border-slate-700 bg-slate-950 px-2.5 py-2 text-white font-mono"
                />
                <button
                  type="submit"
                  className="rounded bg-slate-800 border border-slate-700 px-3 py-2 text-white hover:bg-slate-700"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Historical Timeline of Materiality Assessments & Snapshots */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
            <History className="h-4 w-4 text-blue-400" />
            <span>Historical Gemini Materiality Assessments ({assessments.length})</span>
          </div>
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {assessments.map((a) => (
              <div
                key={a.assessment_id}
                className="rounded-lg border border-slate-800 bg-slate-950 p-3.5 text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                      a.materiality_level === "material"
                        ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                        : a.materiality_level === "non_material"
                        ? "bg-blue-500/20 text-blue-300"
                        : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {a.materiality_level}
                  </span>
                  <span className="font-mono text-[11px] text-slate-400">
                    {new Date(a.evaluated_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-slate-200">{a.executive_summary}</p>
                {a.impacted_finos_risk_ids.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {a.impacted_finos_risk_ids.map((rid) => (
                      <span
                        key={rid}
                        className="rounded bg-rose-950/80 border border-rose-500/30 px-1.5 py-0.5 font-mono text-[10px] text-rose-300"
                      >
                        {rid}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>
              Archived S3 Snapshots ({snapshots.length}) & Audit Signoffs ({signoffs.length})
            </span>
          </div>
          <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1 text-xs">
            {snapshots.map((sn) => (
              <div
                key={sn.snapshot_id}
                className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1"
              >
                <div className="flex items-center justify-between font-mono text-[11px] text-slate-400">
                  <span>SHA256: {sn.content_sha256_hash.slice(0, 20)}...</span>
                  <span>{new Date(sn.captured_at).toLocaleString()}</span>
                </div>
                <div className="font-mono text-[10px] text-blue-400 break-all">
                  {sn.s3_archive_uri}
                </div>
                <div className="text-slate-300 line-clamp-2 font-mono text-[11px]">
                  {sn.raw_extracted_text}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
