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
    <section className="form-panel">
      <div className="form-panel-header">
        <div>
          <h2 className="form-panel-title">Analyze a public link</h2>
          <p className="form-panel-copy">YouTube and Facebook previews only.</p>
        </div>
        <span className="form-chip">Preview-based scan</span>
      </div>

      <AlertMessage message={error} />

      <form onSubmit={handleSubmit} className="d-grid gap-3">
        <div className="url-input-shell">
          <label htmlFor="source-url" className="form-label fw-semibold">
            Paste a public URL
          </label>
          <input
            id="source-url"
            type="url"
            className="form-control form-control-lg url-input"
            placeholder="https://www.youtube.com/watch?v=..."
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <div className="form-note">Private or login-gated links cannot be analyzed.</div>
        </div>

        <div className="action-button-row">
          <button type="submit" className="btn btn-primary btn-lg action-button" disabled={loading}>
            {loading ? "Analyzing..." : "Analyze URL"}
          </button>
        </div>
      </form>
    </section>
  );
}
