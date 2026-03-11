import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { listBuilds, cleanupBuilds, iconUrl, type Build } from "../services/apiClient";

export function Builds() {
  const [builds, setBuilds] = useState<Build[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const [cleanupDays, setCleanupDays] = useState(30);
  const [showCleanup, setShowCleanup] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<string | null>(null);

  const load = (p: number) => {
    setLoading(true);
    listBuilds(p, 20)
      .then((r) => {
        setBuilds(r.builds);
        setTotal(r.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(page);
  }, [page]);

  const handleCleanup = async () => {
    setCleaning(true);
    setCleanupResult(null);
    try {
      const r = await cleanupBuilds(cleanupDays);
      setCleanupResult(`Removed ${r.builds_removed} build(s) older than ${cleanupDays} days.`);
      load(1);
      setPage(1);
    } catch {
      setCleanupResult("Cleanup failed.");
    } finally {
      setCleaning(false);
      setShowCleanup(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  const statusClass = (s: string) =>
    s === "done"
      ? "bg-green-100 text-green-800"
      : s === "failed"
      ? "bg-red-100 text-red-800"
      : "bg-blue-100 text-blue-800";

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Builds</h1>
        <button
          type="button"
          onClick={() => { setShowCleanup((v) => !v); setCleanupResult(null); }}
          className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-gray-50"
        >
          {showCleanup ? "Cancel" : "Cleanup Old Builds"}
        </button>
      </div>

      {showCleanup && (
        <div className="flex items-center gap-3 rounded-lg border bg-white p-4 shadow-sm">
          <span className="text-sm">Remove finished/failed builds older than</span>
          <input
            type="number"
            min={1}
            max={365}
            value={cleanupDays}
            onChange={(e) => setCleanupDays(Number(e.target.value))}
            className="w-20 rounded border px-2 py-1 text-sm text-center"
          />
          <span className="text-sm">days</span>
          <button
            type="button"
            onClick={handleCleanup}
            disabled={cleaning}
            className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {cleaning ? "Cleaning…" : "Run Cleanup"}
          </button>
        </div>
      )}

      {cleanupResult && (
        <div className="rounded bg-green-50 px-4 py-3 text-green-800 text-sm">{cleanupResult}</div>
      )}

      {builds.length === 0 ? (
        <p className="text-gray-600">No builds yet. Upload an IPA from Dashboard.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-50">
              <tr>
                <th className="px-4 py-2 font-medium">App</th>
                <th className="px-4 py-2 font-medium">Bundle ID</th>
                <th className="px-4 py-2 font-medium">Version</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Created</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {builds.map((b) => (
                <tr key={b.uuid} className="border-b last:border-0">
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      {b.status === "done" && (
                        <img
                          src={b.icon_url || iconUrl(b.uuid)}
                          alt=""
                          width={32}
                          height={32}
                          className="rounded"
                          onError={(e) => (e.currentTarget.style.display = "none")}
                        />
                      )}
                      <span className="font-medium">{b.app_name || b.uuid.slice(0, 8)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2 text-gray-600">{b.bundle_id || "—"}</td>
                  <td className="px-4 py-2">{b.short_version ? `v${b.short_version}` : "—"}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusClass(b.status)}`}>
                      {b.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-600">
                    {b.created_at ? new Date(b.created_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-2">
                    <RouterLink
                      to={`/builds/${b.uuid}`}
                      className="text-blue-600 hover:underline"
                    >
                      View
                    </RouterLink>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded border px-3 py-1 text-sm disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= totalPages}
            className="rounded border px-3 py-1 text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
