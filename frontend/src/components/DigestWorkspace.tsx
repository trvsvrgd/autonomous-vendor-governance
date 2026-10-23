import React, { useEffect, useState } from "react";
import { Clock, MailCheck, RefreshCw, Send } from "lucide-react";
import { governanceApi } from "../api/client";
import { DigestOwnerGroup } from "../types/governance";

export const DigestWorkspace: React.FC = () => {
  const [windowHours, setWindowHours] = useState<number>(24);
  const [groups, setGroups] = useState<DigestOwnerGroup[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [dispatching, setDispatching] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDigestPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await governanceApi.previewDigests(windowHours);
      setGroups(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDigestPreview();
  }, [windowHours]);

  const handleDispatchNow = async () => {
    setDispatching(true);
    setError(null);
    try {
      const res = await governanceApi.dispatchDigests(windowHours);
      setStatusMessage(
        `Non-Material Digest dispatched at ${new Date(
          res.dispatched_at
        ).toLocaleTimeString()}: ${res.owners_notified} Business Owners notified across ${
          res.total_assessments_digested
        } non-material assessments via Amazon SES & Slack/Teams webhooks.`
      );
      await loadDigestPreview();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Non-Material Digest Engine (FINOS-OP-11 Oversight Fatigue Prevention)
          </h1>
          <p className="text-sm text-slate-400">
            Aggregates minor UI, latency, formatting, and bug-fix vendor updates over 24 hours or 7 days grouped by Business Owner.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="inline-flex rounded-lg border border-slate-700 bg-slate-900 p-1 text-xs">
            <button
              onClick={() => setWindowHours(24)}
              className={`rounded px-3 py-1 font-medium ${
                windowHours === 24
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Prior 24 Hours
            </button>
            <button
              onClick={() => setWindowHours(168)}
              className={`rounded px-3 py-1 font-medium ${
                windowHours === 168
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Prior 7 Days
            </button>
          </div>

          <button
            onClick={handleDispatchNow}
            disabled={dispatching}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            {dispatching ? "Dispatching..." : "Dispatch Digest Batch Now"}
          </button>

          <button
            onClick={() => void loadDigestPreview()}
            className="rounded-lg border border-slate-700 bg-slate-900 p-2 text-slate-300 hover:bg-slate-800"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {statusMessage && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-xs text-emerald-200 flex items-center gap-2">
          <MailCheck className="h-4 w-4 shrink-0 text-emerald-400" />
          <span>{statusMessage}</span>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-xs text-rose-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4">
        {groups.map((group) => (
          <div
            key={group.owner_id}
            className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <h2 className="text-base font-bold text-white">
                  {group.owner_full_name}{" "}
                  <span className="text-xs font-normal text-slate-400">
                    ({group.department})
                  </span>
                </h2>
                <div className="text-xs text-slate-400 font-mono">
                  Recipient: {group.owner_email}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/20 border border-blue-500/40 px-3 py-1 text-blue-300 font-semibold">
                  <Clock className="h-3.5 w-3.5" />
                  {group.items.length} Non-Material Updates ({windowHours}h Window)
                </span>
              </div>
            </div>

            <div className="divide-y divide-slate-800/70">
              {group.items.map((item) => (
                <div
                  key={item.signoff_id}
                  className="py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-100">
                        {item.vendor_legal_name}
                      </span>
                      <span className="font-mono text-slate-400">
                        ({item.vendor_primary_domain})
                      </span>
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-mono uppercase ${
                          item.review_status === "digest_sent"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "bg-amber-500/20 text-amber-300"
                        }`}
                      >
                        {item.review_status}
                      </span>
                    </div>
                    <p className="text-slate-300">{item.executive_summary}</p>
                  </div>
                  <div className="text-right text-[11px] text-slate-400 shrink-0 font-mono">
                    {new Date(item.evaluated_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {!loading && groups.length === 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-12 text-center text-xs text-slate-400">
            No Non-Material vendor assessments recorded in the prior {windowHours} hours.
          </div>
        )}
      </div>
    </div>
  );
};
