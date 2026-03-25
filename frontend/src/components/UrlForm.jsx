import { useState } from "react";

import AlertMessage from "./AlertMessage";

const SUPPORTED_HOSTS = ["youtube.com", "youtu.be", "facebook.com", "fb.watch"];

function looksSupported(url) {
  return SUPPORTED_HOSTS.some((host) => url.includes(host));
}

export default function UrlForm({ loading, onSubmit }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmed = url.trim();
    if (!trimmed) {
      setError("Enter a public YouTube or Facebook URL.");
      return;
    }

    if (!looksSupported(trimmed)) {
      setError("Only public YouTube and Facebook links are supported.");
      return;
    }

    setError("");
    await onSubmit(trimmed);
  }

  return (
    <div className="card border-0 shadow-sm h-100">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between align-items-start mb-3">
          <div>
            <h2 className="h5 mb-1">Analyze URL</h2>
            <p className="text-secondary mb-0">Public YouTube thumbnails and Facebook previews only. Full video and audio are not fetched in URL mode.</p>
          </div>
          <span className="badge text-bg-light">Preview-based</span>
        </div>

        <AlertMessage message={error} />

        <form onSubmit={handleSubmit} className="d-grid gap-3">
          <div>
            <label htmlFor="source-url" className="form-label fw-semibold">
              Public link
            </label>
            <input
              id="source-url"
              type="url"
              className="form-control form-control-lg"
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
            <div className="form-text">
              Facebook content must expose a public preview image. Private or login-gated links will fail.
            </div>
          </div>

          <button type="submit" className="btn btn-outline-primary btn-lg" disabled={loading}>
            {loading ? "Analyzing..." : "Analyze URL"}
          </button>
        </form>
      </div>
    </div>
  );
}
