import { useEffect, useState } from "react";
import {
  getProfileStatus,
  checkUpdateProfile,
  regenerateProfile,
  type ProfileStatus,
  type CheckUpdateResponse,
} from "../services/apiClient";

export function Profiles() {
  const [status, setStatus] = useState<ProfileStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  const [checkResult, setCheckResult] = useState<CheckUpdateResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const loadStatus = () => {
    setLoadingStatus(true);
    getProfileStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoadingStatus(false));
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleCheckUpdate = async () => {
    setChecking(true);
    setActionError(null);
    setActionSuccess(null);
    setCheckResult(null);
    try {
      const result = await checkUpdateProfile(false);
      setCheckResult(result);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Check failed");
    } finally {
      setChecking(false);
    }
  };

  const handleRegenerate = async (autoRegenerate = false) => {
    if (!status?.latest) return;
    setRegenerating(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      if (autoRegenerate) {
        const result = await checkUpdateProfile(true);
        if (result.regenerated) {
          setActionSuccess(`Profile regenerated with ${result.enabled_devices} enabled devices.`);
        } else {
          setActionSuccess("Profile is already up to date.");
        }
        setCheckResult(result);
      } else {
        const bundleId = status.latest.name.includes("*") ? "*" : status.latest.name;
        const result = await regenerateProfile(bundleId);
        setActionSuccess(result.message);
      }
      loadStatus();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Regeneration failed");
    } finally {
      setRegenerating(false);
    }
  };

  if (loadingStatus) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (!status) {
    return <p className="text-gray-600">Unable to load profile status.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Profile Status</h1>
          <p className="text-gray-600 text-sm mt-1">
            Current Ad Hoc profile status. On upload, the pipeline will reuse or create a profile automatically.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleCheckUpdate}
            disabled={checking || regenerating}
            className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            {checking ? "Checking…" : "Check Update"}
          </button>
          <button
            type="button"
            onClick={() => handleRegenerate(true)}
            disabled={checking || regenerating}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {regenerating ? "Regenerating…" : "Regenerate Profile"}
          </button>
        </div>
      </div>

      {status.error && (
        <div className="rounded bg-red-50 p-4 text-red-700 text-sm">{status.error}</div>
      )}
      {actionError && (
        <div className="rounded bg-red-50 p-4 text-red-700 text-sm">{actionError}</div>
      )}
      {actionSuccess && (
        <div className="rounded bg-green-50 p-4 text-green-800 text-sm">{actionSuccess}</div>
      )}

      <div className="rounded-lg border bg-white p-6 shadow-sm space-y-3">
        <div className="flex items-center gap-2">
          <span className="font-semibold">Coverage</span>
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              status.coverage ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"
            }`}
          >
            {status.coverage ? "All enabled devices covered" : "Missing devices"}
          </span>
        </div>
        <p className="text-sm text-gray-600">Enabled devices: {status.enabled_count}</p>
        {status.latest && (
          <>
            <p className="text-sm">
              Latest profile:{" "}
              <span className="font-medium">{status.latest.name}</span>
              {status.latest.expiration_date && (
                <span className="text-gray-500 ml-1">
                  (expires: {new Date(status.latest.expiration_date).toLocaleDateString()})
                </span>
              )}
            </p>
            {status.latest.device_count != null && (
              <p className="text-sm">Devices in profile: {status.latest.device_count}</p>
            )}
          </>
        )}
        {status.active_path && (
          <p className="break-all font-mono text-xs text-gray-500">
            Active: {status.active_path}
          </p>
        )}
      </div>

      {checkResult && (
        <div className="rounded-lg border bg-white p-6 shadow-sm space-y-2">
          <h2 className="font-semibold text-sm">Update Check Result</h2>
          <p className="text-sm">
            Status:{" "}
            <span
              className={`font-medium ${checkResult.needs_update ? "text-amber-700" : "text-green-700"}`}
            >
              {checkResult.needs_update ? "Update needed" : "Up to date"}
            </span>
          </p>
          <p className="text-sm text-gray-600">
            Total devices: {checkResult.total_devices} &nbsp;|&nbsp; Enabled:{" "}
            {checkResult.enabled_devices}
          </p>
          {checkResult.missing_enabled_devices.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-700 mt-2 mb-1">
                Missing enabled devices ({checkResult.missing_enabled_devices.length}):
              </p>
              <ul className="text-xs text-gray-600 space-y-0.5">
                {checkResult.missing_enabled_devices.map((d) => (
                  <li key={d.udid} className="font-mono">
                    {d.name} — {d.udid}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {checkResult.regenerated && (
            <p className="text-sm text-green-700 font-medium">Profile was regenerated.</p>
          )}
        </div>
      )}

      {status.missing_devices.length > 0 && (
        <div className="rounded-lg border bg-white p-6 shadow-sm">
          <h2 className="mb-2 text-sm font-semibold">
            Missing from profile ({status.missing_devices.length})
          </h2>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 font-medium">Name</th>
                <th className="py-2 font-medium">UDID</th>
                <th className="py-2 font-medium">Platform</th>
              </tr>
            </thead>
            <tbody>
              {status.missing_devices.map((d) => (
                <tr key={d.udid} className="border-b last:border-0">
                  <td className="py-2">{d.name}</td>
                  <td className="font-mono text-xs py-2">{d.udid}</td>
                  <td className="py-2">{d.platform}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
