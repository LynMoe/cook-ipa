import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadIpa, submitIpaUrl } from "../services/apiClient";

export function Dashboard() {
  const navigate = useNavigate();
  const [fileLoading, setFileLoading] = useState(false);
  const [urlLoading, setUrlLoading] = useState(false);
  const [fileMessage, setFileMessage] = useState<{ type: "error" | "success"; text: string } | null>(null);
  const [urlMessage, setUrlMessage] = useState<{ type: "error" | "success"; text: string } | null>(null);
  const [ipaUrl, setIpaUrl] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function onSelectFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".ipa")) {
      setFileMessage({ type: "error", text: "Only .ipa files are accepted" });
      return;
    }
    setFileMessage(null);
    setFileLoading(true);
    try {
      const { build } = await uploadIpa(file);
      setFileMessage({ type: "success", text: "Upload started" });
      navigate(`/builds/${build.uuid}`);
    } catch (err) {
      setFileMessage({ type: "error", text: String(err) });
    } finally {
      setFileLoading(false);
      e.target.value = "";
    }
  }

  async function onSubmitUrl(e: React.FormEvent) {
    e.preventDefault();
    const url = ipaUrl.trim();
    if (!url) return;
    setUrlMessage(null);
    setUrlLoading(true);
    try {
      const { build } = await submitIpaUrl(url);
      setUrlMessage({ type: "success", text: "Download started" });
      navigate(`/builds/${build.uuid}`);
    } catch (err) {
      setUrlMessage({ type: "error", text: String(err) });
    } finally {
      setUrlLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Submit IPA</h1>
      <p className="text-gray-600">
        Re-sign an IPA with your Ad Hoc profile. Profile is resolved automatically.
      </p>

      {/* Upload File */}
      <div className="rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-medium text-gray-800">Upload File</h2>
        {fileLoading ? (
          <div className="flex justify-center py-6">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : (
          <div className="space-y-3">
            {fileMessage && (
              <div
                className={`rounded px-3 py-2 text-sm ${
                  fileMessage.type === "error" ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"
                }`}
              >
                {fileMessage.text}
              </div>
            )}
            <input ref={inputRef} type="file" accept=".ipa" onChange={onSelectFile} className="hidden" />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
            >
              Choose .ipa file
            </button>
          </div>
        )}
      </div>

      {/* From URL */}
      <div className="rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-medium text-gray-800">From URL</h2>
        {urlLoading ? (
          <div className="flex justify-center py-6">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : (
          <form onSubmit={onSubmitUrl} className="space-y-3">
            {urlMessage && (
              <div
                className={`rounded px-3 py-2 text-sm ${
                  urlMessage.type === "error" ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"
                }`}
              >
                {urlMessage.text}
              </div>
            )}
            <input
              type="url"
              value={ipaUrl}
              onChange={(e) => setIpaUrl(e.target.value)}
              placeholder="https://example.com/path/to/app.ipa"
              required
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500">
              The server will download the IPA directly from this URL and begin processing.
            </p>
            <button
              type="submit"
              disabled={!ipaUrl.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Process IPA
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
