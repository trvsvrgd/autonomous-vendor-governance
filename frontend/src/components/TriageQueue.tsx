import React, { useEffect, useState } from "react";
import {
  AlertOctagon,
  CheckCircle2,
  FileDiff,
  Lock,
  RefreshCw,
  Scale,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { governanceApi } from "../api/client";
import { TriageQueueItem } from "../types/governance";

export const TriageQueue: React.FC = () => {
  const [items, setItems] = useState<TriageQueueItem[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [materialityFilter, setMaterialityFilter] = useState<string>("material");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [decisionNotes, setDecisionNotes] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await governanceApi.listTriageQueue({
        materiality_level: materialityFilter || undefined,
        review_status: statusFilter || undefined,
      });
      setItems(res);
      if (selectedIdx >= res.length) {
        setSelectedIdx(0);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadQueue();
  }, [materialityFilter, statusFilter]);

  const activeItem = items[selectedIdx] || null;

  const handleDecision = async (
    action: "approve" | "require_remediation" | "escalate_to_legal"
  ) => {
    if (!activeItem) return;
    if (decisionNotes.trim().length < 5) {
      setError("Please enter at least 5 characters of audit decision notes before signing.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const signed = await governanceApi.submitSignoffDecision(
        activeItem.signoff.signoff_id,
        {
          action,
          owner_decision_notes: decisionNotes,
          actor_owner_id: activeItem.assigned_owner.owner_id,
        }
      );
      setFeedback(
        `Immutable Governance Signoff recorded (${signed.review_status.toUpperCase()}) with cryptographic hash ${signed.cryptographic_signature_hash?.slice(0, 28)}...`
      );
      setDecisionNotes("");
      await loadQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const renderSideBySideDiff = (prevText: string, newText: string) => {
    const prevLines = prevText.split("\n");
    const newLines = newText.split("\n");
    const prevSet = new Set(prevLines.map((l) => l.trim()));
    const newSet = new Set(newLines.map((l) => l.trim()));

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 font-mono text-xs">
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 overflow-x-auto max-h-80 overflow-y-auto">
          <div className="text-[11px] font-sans font-semibold uppercase tracking-wider text-slate-400 mb-2 border-b border-slate-800 pb-1">
            Baseline / Prior Snapshot
          </div>
          {prevLines.map((line, i) => {
            const removed = line.trim() && !newSet.has(line.trim());
            return (
              <div
                key={i}
                className={`px-2 py-0.5 whitespace-pre-wrap break-words ${
                  removed
                    ? "bg-rose-950/60 text-rose-300 border-l-2 border-rose-500"
                    : "text-slate-400"
                }`}
              >
                {removed ? `- ${line}` : `  ${line}`}
              </div>
            );
          })}
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 overflow-x-auto max-h-80 overflow-y-auto">
          <div className="text-[11px] font-sans font-semibold uppercase tracking-wider text-blue-400 mb-2 border-b border-slate-800 pb-1">
            New Captured Snapshot (Evaluated by Gemini)
          </div>
          {newLines.map((line, i) => {
            const added = line.trim() && !prevSet.has(line.trim());
            return (
              <div
                key={i}
                className={`px-2 py-0.5 whitespace-pre-wrap break-words ${
                  added
                    ? "bg-emerald-950/60 text-emerald-300 border-l-2 border-emerald-500"
                    : "text-slate-300"
                }`}
              >
                {added ? `+ ${line}` : `  ${line}`}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Material Change Triage & Cryptographic Signoff Queue
          </h1>
          <p className="text-sm text-slate-400">
            Review Gemini executive summaries, inspect side-by-side ULA/web snapshot diffs, and execute auditable FINOS v2 signoffs.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={materialityFilter}
            onChange={(e) => setMaterialityFilter(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Materiality Levels</option>
            <option value="material">Material Alerts Only</option>
            <option value="non_material">Non-Material Only</option>
            <option value="baseline">Baseline Captures</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Review Statuses</option>
            <option value="awaiting_review">Awaiting Review</option>
            <option value="approved">Approved</option>
            <option value="mitigated">Remediation Required</option>
            <option value="rejected">Escalated to Legal / Restricted</option>
          </select>

          <button
            onClick={() => void loadQueue()}
            className="rounded-lg border border-slate-700 bg-slate-900 p-2 text-slate-300 hover:bg-slate-800"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {feedback && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-xs text-emerald-200">
          {feedback}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-xs text-rose-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Queue Selector */}
        <div className="lg:col-span-4 space-y-2.5 max-h-[750px] overflow-y-auto pr-1">
          {items.map((item, idx) => {
            const isSelected = idx === selectedIdx;
            const isMaterial = item.assessment.materiality_level === "material";
            return (
              <div
                key={item.signoff.signoff_id}
                onClick={() => setSelectedIdx(idx)}
                className={`cursor-pointer rounded-xl border p-3.5 transition ${
                  isSelected
                    ? "border-blue-500 bg-blue-950/30"
                    : "border-slate-800 bg-slate-900/70 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm text-white">
                    {item.vendor_legal_name}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                      isMaterial
                        ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                        : item.assessment.materiality_level === "non_material"
                        ? "bg-blue-500/20 text-blue-300"
                        : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {item.assessment.materiality_level}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-1 line-clamp-2">
                  {item.assessment.executive_summary}
                </div>
                <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Owner: {item.assigned_owner.full_name}</span>
                  <span className="font-mono text-slate-300">
                    {item.signoff.review_status}
                  </span>
                </div>
              </div>
            );
          })}

          {!loading && items.length === 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-xs text-slate-400">
              No assessments in queue for the selected filter.
            </div>
          )}
        </div>

        {/* Right Detailed Triage & Signoff Panel */}
        <div className="lg:col-span-8">
          {activeItem ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-6 space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-white">
                      {activeItem.vendor_legal_name}
                    </h2>
                    <span className="text-xs font-mono text-slate-400">
                      ({activeItem.vendor_primary_domain})
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    Source: <span className="font-mono text-slate-300">{activeItem.source_type}</span> •{" "}
                    <span className="font-mono text-slate-300">{activeItem.source_uri}</span>
                  </div>
                </div>
                <div className="text-right text-xs">
                  <div className="text-slate-400">
                    Evaluated by:{" "}
                    <span className="font-mono text-blue-300">
                      {activeItem.assessment.gemini_model_identifier}
                    </span>
                  </div>
                  <div className="text-slate-500 mt-0.5">
                    {new Date(activeItem.assessment.evaluated_at).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Gemini Executive Summary */}
              <div className="rounded-lg border border-blue-500/30 bg-blue-950/20 p-4">
                <div className="text-xs font-bold uppercase tracking-wider text-blue-300 mb-1">
                  Gemini Governance Evaluator Executive Summary
                </div>
                <p className="text-sm text-slate-100 leading-relaxed">
                  {activeItem.assessment.executive_summary}
                </p>
                <div className="mt-3 pt-3 border-t border-blue-500/20 text-xs text-slate-300 whitespace-pre-line">
                  <span className="font-semibold text-blue-300">Recommended Actions: </span>
                  {activeItem.assessment.recommended_actions}
                </div>
              </div>

              {/* Triggered FINOS v2 Risk Controls */}
              <div>
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300 mb-2.5">
                  <ShieldAlert className="h-4 w-4 text-rose-400" />
                  <span>
                    Triggered FINOS AI Governance Framework v2 Controls (
                    {activeItem.triggered_finos_controls.length})
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  {activeItem.triggered_finos_controls.map((ctrl) => (
                    <div
                      key={ctrl.risk_id}
                      className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-bold text-rose-300">
                          {ctrl.risk_id}: {ctrl.risk_name}
                        </span>
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-300">
                          {ctrl.category_group}
                        </span>
                      </div>
                      <p className="text-slate-400 text-[11px] mt-1">
                        {ctrl.description}
                      </p>
                      <div className="mt-2 pt-2 border-t border-slate-800/80 text-[10px] text-slate-400 space-y-0.5">
                        <div>
                          <b className="text-slate-300">SR 11-7:</b> {ctrl.sr_11_7_mapping}
                        </div>
                        <div>
                          <b className="text-slate-300">NIST RMF:</b> {ctrl.nist_ai_rmf_mapping}
                        </div>
                        <div>
                          <b className="text-slate-300">EU AI Act:</b> {ctrl.eu_ai_act_mapping}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Side-by-Side Visual Snapshot Diff */}
              <div>
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300 mb-2.5">
                  <FileDiff className="h-4 w-4 text-emerald-400" />
                  <span>Side-by-Side ULA / Web Snapshot Visual Diff</span>
                </div>
                {renderSideBySideDiff(
                  activeItem.previous_snapshot_text,
                  activeItem.new_snapshot_text
                )}
              </div>

              {/* Cryptographic Audit Signoff Controls */}
              <div className="rounded-xl border border-slate-700 bg-slate-950 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-200">
                    <Lock className="h-4 w-4 text-amber-400" />
                    <span>Accountable Business Owner Cryptographic Signoff</span>
                  </div>
                  <span className="text-xs text-slate-400">
                    Assigned: <b className="text-white">{activeItem.assigned_owner.full_name}</b> (
                    {activeItem.assigned_owner.email_address})
                  </span>
                </div>

                {activeItem.signoff.cryptographic_signature_hash && (
                  <div className="rounded border border-emerald-500/30 bg-emerald-950/30 p-2.5 text-[11px] text-emerald-200 font-mono break-all">
                    <div>
                      Current Status: <b>{activeItem.signoff.review_status.toUpperCase()}</b> •
                      Decided At: {activeItem.signoff.decided_at}
                    </div>
                    <div>Signature Hash: {activeItem.signoff.cryptographic_signature_hash}</div>
                    <div className="font-sans text-slate-300 mt-1">
                      Notes: {activeItem.signoff.owner_decision_notes}
                    </div>
                  </div>
                )}

                <textarea
                  rows={3}
                  value={decisionNotes}
                  onChange={(e) => setDecisionNotes(e.target.value)}
                  placeholder="Enter mandatory governance audit rationale, compensating controls, or legal escalation instructions..."
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs text-white focus:border-blue-500 focus:outline-none"
                />

                <div className="flex flex-wrap items-center justify-end gap-3">
                  <button
                    disabled={submitting}
                    onClick={() => void handleDecision("approve")}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    Approve Material Change
                  </button>

                  <button
                    disabled={submitting}
                    onClick={() => void handleDecision("require_remediation")}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-2 text-xs font-semibold text-white hover:bg-amber-500 disabled:opacity-50"
                  >
                    <Wrench className="h-4 w-4" />
                    Require Vendor Remediation
                  </button>

                  <button
                    disabled={submitting}
                    onClick={() => void handleDecision("escalate_to_legal")}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
                  >
                    <Scale className="h-4 w-4" />
                    Escalate to Legal & Restrict
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-12 text-center text-sm text-slate-400">
              <AlertOctagon className="h-8 w-8 text-slate-600 mx-auto mb-2" />
              Select an assessment from the queue on the left to inspect its diff and record a cryptographic signoff.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
