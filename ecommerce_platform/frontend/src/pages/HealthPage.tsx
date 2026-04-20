/**
 * pages/HealthPage.tsx — Backend service status pills.
 *
 * Calls `GET /health` and renders one pill per backing service
 * (postgres, redis, elasticsearch). Useful for confirming that the local
 * `docker compose up` stack is fully healthy before debugging anything else.
 *
 * The status string returned by the backend is "ok" when the service is
 * reachable, and "error: ..." otherwise.
 */

import { useCallback, useEffect, useState } from "react";

import { getHealth } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import type { HealthStatus } from "../types";

export default function HealthPage() {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null);

  // Wrapped in useCallback so the "Refresh" button can call it directly.
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getHealth();
      setStatus(data);
      setLastCheckedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health check failed");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Service health</h1>
        <button
          onClick={refresh}
          disabled={loading}
          className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Checking…" : "Refresh"}
        </button>
      </div>

      <p className="mt-1 text-sm text-slate-500">
        Calls <code className="rounded bg-slate-100 px-1">GET /health</code> on
        the FastAPI backend. Each service is pinged on every request.
      </p>

      <div className="mt-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
        {loading && !status ? (
          <LoadingSpinner message="Pinging services…" />
        ) : error ? (
          <p className="rounded-xl bg-red-50 p-4 text-sm text-red-700">
            <strong>Backend unreachable:</strong> {error}
            <br />
            Is the API running on{" "}
            <code className="rounded bg-white/60 px-1">
              http://localhost:8000
            </code>
            ?
          </p>
        ) : status ? (
          <ul className="space-y-3">
            <ServicePill name="PostgreSQL" status={status.postgres} />
            <ServicePill name="Valkey (Redis)" status={status.redis} />
            <ServicePill name="Elasticsearch" status={status.elasticsearch} />
          </ul>
        ) : null}

        {lastCheckedAt && (
          <p className="mt-5 text-right text-xs text-slate-400">
            Last checked at {lastCheckedAt.toLocaleTimeString()}
          </p>
        )}
      </div>
    </div>
  );
}

function ServicePill({ name, status }: { name: string; status: string }) {
  const ok = status === "ok";
  return (
    <li className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 p-4">
      <span className="font-medium text-slate-800">{name}</span>
      <span
        className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${
          ok
            ? "bg-emerald-100 text-emerald-700"
            : "bg-red-100 text-red-700"
        }`}
      >
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            ok ? "bg-emerald-500" : "bg-red-500"
          }`}
        />
        {ok ? "OK" : status}
      </span>
    </li>
  );
}
