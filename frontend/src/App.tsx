import React, { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  FileCheck2,
  Inbox,
  LayoutGrid,
  Mail,
  Shield,
} from "lucide-react";
import { governanceApi } from "./api/client";
import { CommandCenter } from "./components/CommandCenter";
import { ComplianceCenter } from "./components/ComplianceCenter";
import { DigestWorkspace } from "./components/DigestWorkspace";
import { TriageQueue } from "./components/TriageQueue";
import { VendorDetail } from "./components/VendorDetail";

type ActiveTab =
  | "command_center"
  | "triage_queue"
  | "digest_engine"
  | "vendor_detail"
  | "compliance_center";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>("command_center");
  const [selectedVendorId, setSelectedVendorId] = useState<string | null>(null);
  const [health, setHealth] = useState<{
    status: string;
    gemini_execution_mode: string;
    gemini_model_id: string;
    finos_v2_controls_seeded: number;
    vendors_monitored: number;
  } | null>(null);

  // Inbound Vendor Notification Listener modal
  const [showInboundModal, setShowInboundModal] = useState<boolean>(false);
  const [inboundSender, setInboundSender] = useState<string>("");
  const [inboundSubject, setInboundSubject] = useState<string>("");
  const [inboundBody, setInboundBody] = useState<string>("");
  const [inboundNotice, setInboundNotice] = useState<string | null>(null);

  const loadHealth = async () => {
    try {
      const h = await governanceApi.getHealth();
      setHealth(h);
    } catch {
      // backend starting up
    }
  };

  useEffect(() => {
    void loadHealth();
  }, [activeTab]);

  const handleSelectVendor = (vendorId: string) => {
    setSelectedVendorId(vendorId);
    setActiveTab("vendor_detail");
  };

  const handleDispatchInboundBulletin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await governanceApi.sendInboundVendorWebhook({
        sender_email_or_domain: inboundSender,
        subject: inboundSubject,
        body_text: inboundBody,
      });
      const assessment = res.assessment as Record<string, unknown>;
      setInboundNotice(
        `Inbound bulletin mapped to vendor & evaluated by Gemini: Materiality = ${String(
          assessment.materiality_level
        ).toUpperCase()}`
      );
      setInboundSubject("");
      setInboundBody("");
      await loadHealth();
    } catch (err) {
      setInboundNotice(
        `Error: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top AWS AVA v5.0 Govern Navigation Bar */}
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white shadow">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-white tracking-tight">
                Autonomous AI Vendor Governance
              </div>
              <div className="text-[11px] text-slate-400">
                FINOS v2 Catalog • CALM 1.0 • AWS AVA v5.0 Govern
              </div>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/90 p-1 text-xs">
            <button
              onClick={() => setActiveTab("command_center")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${
                activeTab === "command_center" || activeTab === "vendor_detail"
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Command Center
            </button>

            <button
              onClick={() => setActiveTab("triage_queue")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${
                activeTab === "triage_queue"
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
              Material Triage & Signoff
            </button>

            <button
              onClick={() => setActiveTab("digest_engine")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${
                activeTab === "digest_engine"
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              <Mail className="h-3.5 w-3.5 text-emerald-400" />
              Non-Material Digests
            </button>

            <button
              onClick={() => setActiveTab("compliance_center")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${
                activeTab === "compliance_center"
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              <FileCheck2 className="h-3.5 w-3.5 text-purple-400" />
              Regulatory & CALM Exporter
            </button>
          </nav>

          <div className="flex items-center gap-2.5 text-xs">
            <button
              onClick={() => setShowInboundModal(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-slate-200 hover:bg-slate-800"
              title="Inbound Vendor Bulletin Webhook & SES Email Listener"
            >
              <Inbox className="h-3.5 w-3.5 text-blue-400" />
              <span className="hidden sm:inline">Inbound Listener</span>
            </button>

            <div className="hidden lg:flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-[11px]">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-slate-400">Gemini Bridge:</span>
              <span className="font-mono font-bold uppercase text-emerald-300">
                {health?.gemini_execution_mode || "harness"}
              </span>
              <span className="text-slate-600">|</span>
              <span className="font-mono text-blue-300">
                {health?.finos_v2_controls_seeded ?? 23} FINOS Controls
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "command_center" && (
          <CommandCenter
            onSelectVendor={handleSelectVendor}
            onNavigateTriage={() => setActiveTab("triage_queue")}
          />
        )}

        {activeTab === "triage_queue" && <TriageQueue />}

        {activeTab === "digest_engine" && <DigestWorkspace />}

        {activeTab === "vendor_detail" && selectedVendorId && (
          <VendorDetail
            vendorId={selectedVendorId}
            onBack={() => setActiveTab("command_center")}
            onOpenTriage={() => setActiveTab("triage_queue")}
          />
        )}

        {activeTab === "compliance_center" && <ComplianceCenter />}
      </main>

      {/* Modal: Inbound Vendor Notification Listener (Webhook / SES Inbound) */}
      {showInboundModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white">
                Inbound Vendor Notification Listener (SES & Verified Webhook)
              </h2>
              <button
                onClick={() => {
                  setShowInboundModal(false);
                  setInboundNotice(null);
                }}
                className="text-xs text-slate-400 hover:text-white"
              >
                Close
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Maps inbound vendor product updates or security bulletins by sender domain to <code className="text-slate-200">vendor_id</code>, archives the raw payload in S3, writes a <code className="text-slate-200">vendor_snapshots</code> record, and triggers Gemini evaluation.
            </p>
            {inboundNotice && (
              <div className="rounded border border-blue-500/40 bg-blue-950/40 p-3 text-xs text-blue-200">
                {inboundNotice}
              </div>
            )}
            <form onSubmit={handleDispatchInboundBulletin} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 mb-1">
                  Sender Email or Vendor Domain
                </label>
                <input
                  required
                  value={inboundSender}
                  onChange={(e) => setInboundSender(e.target.value)}
                  placeholder="security-bulletins@anthropic.com"
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1">Bulletin Subject</label>
                <input
                  required
                  value={inboundSubject}
                  onChange={(e) => setInboundSubject(e.target.value)}
                  placeholder="Q4 Product Update: Autonomous MCP Tool Execution & Retention Policy Change"
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1">
                  Bulletin / SES Email Body
                </label>
                <textarea
                  required
                  rows={4}
                  value={inboundBody}
                  onChange={(e) => setInboundBody(e.target.value)}
                  placeholder="Effective immediately, we are enabling autonomous execution via Model Context Protocol (MCP) servers and Agent-to-Agent (A2A) delegation..."
                  className="w-full rounded border border-slate-700 bg-slate-950 p-2.5 text-white font-mono"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowInboundModal(false)}
                  className="rounded border border-slate-700 px-4 py-2 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-500"
                >
                  Ingest & Evaluate Bulletin
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
