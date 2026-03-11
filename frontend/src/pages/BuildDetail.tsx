import { useEffect, useState, useRef } from "react";
import { useParams, Link as RouterLink } from "react-router-dom";
import QRCode from "qrcode";
import { getBuild, getBuildLogs, buildLogsStreamUrl, iconUrl, type Build } from "../services/apiClient";

export function BuildDetail() {
  const { uuid } = useParams<{ uuid: string }>();
  const [build, setBuild] = useState<Build | null>(null);
  const [logs, setLogs] = useState<{ id: number; message: string; level: string }[]>([]);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!uuid) return;
    getBuild(uuid)
      .then((r) => {
        setBuild(r.build);
        if (["done", "failed"].includes(r.build.status)) {
          getBuildLogs(uuid, 0).then((res) => setLogs(res.logs)).catch(() => {});
        }
      })
      .catch(() => setBuild(null))
      .finally(() => setLoading(false));
  }, [uuid]);

  useEffect(() => {
    if (!uuid || !build || ["done", "failed"].includes(build.status)) return;
    const es = new EventSource(buildLogsStreamUrl(uuid));
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.message !== undefined) {
          setLogs((prev) => [...prev, { id: data.id ?? prev.length, message: data.message, level: data.level ?? "info" }]);
        }
      } catch (_) {}
    };

    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data = JSON.parse((e as MessageEvent).data);
        if (data.status && ["done", "failed"].includes(data.status)) {
          getBuild(uuid!).then((r) => setBuild(r.build)).catch(() => setBuild((b) => (b ? { ...b, status: data.status } : null)));
          es.close();
        }
      } catch (_) {
        getBuild(uuid!).then((r) => setBuild(r.build)).finally(() => es.close());
      }
    });

    es.onerror = () => es.close();
    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [uuid, build]);

  useEffect(() => {
    const el = logContainerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  useEffect(() => {
    if (!build?.install_url) return;
    QRCode.toDataURL(build.install_url, { width: 200, margin: 1 }).then(setQrDataUrl).catch(() => setQrDataUrl(null));
  }, [build?.install_url]);

  if (loading && !build) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }
  if (!build) {
    return (
      <div className="space-y-4">
        <p>Build not found.</p>
        <RouterLink to="/builds" className="text-blue-600 hover:underline">
          Back to Builds
        </RouterLink>
      </div>
    );
  }

  const statusClass =
    build.status === "done" ? "bg-green-100 text-green-800" : build.status === "failed" ? "bg-red-100 text-red-800" : "bg-blue-100 text-blue-800";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        {build.status === "done" && (
          <img
            src={build.icon_url || iconUrl(build.uuid)}
            alt=""
            width={48}
            height={48}
            className="rounded-lg"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        )}
        <div>
          <h1 className="text-2xl font-semibold">
            {build.app_name || build.bundle_id || build.uuid.slice(0, 8)}
          </h1>
          <p className="text-sm text-gray-600">
            {build.bundle_id} {build.short_version && `· v${build.short_version}`}
          </p>
        </div>
        <span className={`rounded px-2 py-1 text-sm font-medium ${statusClass}`}>{build.status}</span>
      </div>

      {build.status === "done" && build.install_url && (
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="font-semibold">Install on device</p>
          <div className="mt-2 flex flex-wrap items-start gap-4">
            {qrDataUrl && (
              <div className="flex flex-col items-center gap-1">
                <img src={qrDataUrl} alt="QR code for install" width={200} height={200} className="rounded border border-gray-200" />
                <span className="text-xs text-gray-500">Scan to install</span>
              </div>
            )}
            <div className="min-w-0 flex-1">
              <a href={build.install_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline break-all text-sm">
                {build.install_url}
              </a>
              <div className="mt-2">
                <a
                  href={build.install_url}
                  className="inline-block rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
                >
                  Open install link
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {build.error_message && (
        <div className="rounded bg-red-50 p-4 text-red-700">{build.error_message}</div>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold">Log</h2>
        <pre
          ref={logContainerRef}
          className="max-h-[400px] overflow-y-auto rounded bg-gray-900 p-4 text-sm text-gray-100"
        >
          {logs.map((l) => (
            <div
              key={l.id}
              className={l.level === "error" ? "text-red-300" : l.level === "success" ? "text-green-300" : ""}
            >
              {l.message}
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}
