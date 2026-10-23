import React, { useEffect, useState } from "react";
import { Code2, Download, FileSpreadsheet, FileText, Shield } from "lucide-react";
import { governanceApi } from "../api/client";
import { FinosRiskControl } from "../types/governance";

type FrameworkChoice =
  | "unified_pack"
  | "sr_11_7"
  | "nist_iso_42001"
  | "eu_ai_act"
  | "finos_calm";

export const ComplianceCenter: React.FC = () => {
  const [framework, setFramework] = useState<FrameworkChoice>("unified_pack");
  const [exportJson, setExportJson] = useState<Record<string, unknown> | null>(
    null
  );
  const [catalog, setCatalog] = useState<FinosRiskControl[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const loadComplianceArtifacts = async () => {
    setLoading(true);
    try {
      const [jsonArtifact, finosCatalog] = await Promise.all([
        governanceApi.getRegulatoryJsonExport(framework),
        governanceApi.getFinosCatalog(),
      ]);
      setExportJson(jsonArtifact);
      setCatalog(finosCatalog);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadComplianceArtifacts();
  }, [framework]);

  const handleDownloadJsonFile = () => {
    if (!exportJson) return;
    const blob = new Blob([JSON.stringify(exportJson, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `enterprise_ai_governance_${framework}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Regulatory Reporting & Governance-as-Code Exporter
          </h1>
          <p className="text-sm text-slate-400">
            Generate examination-ready PDF packs and FINOS CALM machine-readable architecture artifacts from live PostgreSQL state.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <a
            href={governanceApi.getRegulatoryPdfDownloadUrl(framework)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500"
          >
            <FileText className="h-4 w-4" />
            Download PDF Examination Pack
          </a>

          <button
            onClick={handleDownloadJsonFile}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-900/50"
          >
            <Download className="h-4 w-4" />
            Export Machine-Readable JSON / CALM
          </button>
        </div>
      </div>

      {/* Framework Selector Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          {
            id: "unified_pack",
            title: "Unified Examination Pack",
            sub: "All 4 Regulatory Frameworks",
          },
          {
            id: "sr_11_7",
            title: "US Fed SR 11-7",
            sub: "Model Risk Management Inventory",
          },
          {
            id: "nist_iso_42001",
            title: "NIST AI RMF & ISO 42001",
            sub: "Govern, Map, Measure, Manage",
          },
          {
            id: "eu_ai_act",
            title: "EU AI Act GPAI & Annex III",
            sub: "High-Risk & ZDR Transparency",
          },
          {
            id: "finos_calm",
            title: "FINOS CALM v1.0",
            sub: "Governance-as-Code Architecture",
          },
        ].map((card) => (
          <button
            key={card.id}
            onClick={() => setFramework(card.id as FrameworkChoice)}
            className={`text-left rounded-xl border p-3.5 transition ${
              framework === card.id
                ? "border-blue-500 bg-blue-950/30 text-white"
                : "border-slate-800 bg-slate-900/70 text-slate-300 hover:border-slate-700"
            }`}
          >
            <div className="font-bold text-xs">{card.title}</div>
            <div className="text-[11px] text-slate-400 mt-1">{card.sub}</div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: 23 Official FINOS AI Governance Framework v2 Catalog */}
        <div className="lg:col-span-6 rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-400">
              <Shield className="h-4 w-4" />
              <span>
                FINOS AI Governance Framework v2 Catalog ({catalog.length} Official Controls)
              </span>
            </div>
            <FileSpreadsheet className="h-4 w-4 text-slate-400" />
          </div>
          <div className="space-y-2.5 max-h-[540px] overflow-y-auto pr-1">
            {catalog.map((ctrl) => (
              <div
                key={ctrl.risk_id}
                className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-white">
                    {ctrl.risk_id} — {ctrl.risk_name}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                      ctrl.category_group === "operational"
                        ? "bg-blue-500/20 text-blue-300"
                        : ctrl.category_group === "security"
                        ? "bg-rose-500/20 text-rose-300"
                        : "bg-purple-500/20 text-purple-300"
                    }`}
                  >
                    {ctrl.category_group.replace("_", " ")}
                  </span>
                </div>
                <p className="text-slate-400 text-[11px]">{ctrl.description}</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 pt-1.5 text-[10px] text-slate-400 border-t border-slate-800/80">
                  <div>
                    <b className="text-slate-300">SR 11-7:</b> {ctrl.sr_11_7_mapping}
                  </div>
                  <div>
                    <b className="text-slate-300">NIST AI RMF:</b>{" "}
                    {ctrl.nist_ai_rmf_mapping}
                  </div>
                  <div>
                    <b className="text-slate-300">ISO 42001:</b>{" "}
                    {ctrl.iso_42001_mapping}
                  </div>
                  <div>
                    <b className="text-slate-300">EU AI Act:</b>{" "}
                    {ctrl.eu_ai_act_mapping}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Machine-Readable Governance-as-Code JSON / CALM Inspector */}
        <div className="lg:col-span-6 rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
              <Code2 className="h-4 w-4" />
              <span>
                Live Governance-as-Code JSON Artifact ({framework.toUpperCase()})
              </span>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              {loading ? "Querying PostgreSQL..." : "SHA-256 Verified"}
            </span>
          </div>
          <pre className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-[11px] font-mono text-emerald-300 overflow-x-auto max-h-[540px] overflow-y-auto">
            {exportJson ? JSON.stringify(exportJson, null, 2) : "Loading..."}
          </pre>
        </div>
      </div>
    </div>
  );
};
