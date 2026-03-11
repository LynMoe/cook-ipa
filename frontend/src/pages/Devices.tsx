import { useEffect, useState } from "react";
import { listDevices, registerDevice, type Device } from "../services/apiClient";

export function Devices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [udid, setUdid] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    listDevices()
      .then((r) => setDevices(r.devices))
      .catch(() => setDevices([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      await registerDevice(name.trim(), udid.trim());
      setSuccess(`Device "${name.trim()}" registered successfully.`);
      setName("");
      setUdid("");
      setShowForm(false);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Devices</h1>
          <p className="text-gray-600 text-sm mt-1">
            Devices registered in your Apple Developer account. Only ENABLED devices are included in Ad Hoc profiles.
          </p>
        </div>
        <button
          type="button"
          onClick={() => { setShowForm((v) => !v); setError(null); setSuccess(null); }}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {showForm ? "Cancel" : "Register Device"}
        </button>
      </div>

      {success && (
        <div className="rounded bg-green-50 px-4 py-3 text-green-800 text-sm">{success}</div>
      )}

      {showForm && (
        <form
          onSubmit={handleRegister}
          className="rounded-lg border bg-white p-4 shadow-sm space-y-3"
        >
          <h2 className="font-semibold text-sm">Register a new device</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Device Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My iPhone"
                required
                className="w-full rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">UDID</label>
              <input
                type="text"
                value={udid}
                onChange={(e) => setUdid(e.target.value)}
                placeholder="00008030-000000000000000"
                required
                className="w-full rounded border px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          {error && <p className="text-red-600 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? "Registering…" : "Register"}
          </button>
        </form>
      )}

      {devices.length === 0 ? (
        <p className="text-gray-600">No devices or unable to load.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-50">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">UDID</th>
                <th className="px-4 py-2 font-medium">Platform</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.udid} className="border-b last:border-0">
                  <td className="px-4 py-2 font-medium">{d.name}</td>
                  <td className="px-4 py-2 font-mono text-xs">{d.udid}</td>
                  <td className="px-4 py-2">{d.platform}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        d.status === "ENABLED"
                          ? "bg-green-100 text-green-800"
                          : "bg-gray-100 text-gray-800"
                      }`}
                    >
                      {d.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
