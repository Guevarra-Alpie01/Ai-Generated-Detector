import { startTransition, useEffect, useState } from "react";

import { fetchDetectionHistory, submitUploadDetection, submitUrlDetection } from "./api/client";
import AlertMessage from "./components/AlertMessage";
import HistoryTable from "./components/HistoryTable";
import LoadingState from "./components/LoadingState";
import ResultCard from "./components/ResultCard";
import UploadForm from "./components/UploadForm";
import UrlForm from "./components/UrlForm";

const EMPTY_HISTORY = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

export default function App() {
  const [activeTab, setActiveTab] = useState("upload");
  const [latestResult, setLatestResult] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState(EMPTY_HISTORY);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyPage, setHistoryPage] = useState(1);

  useEffect(() => {
    loadHistory(1);
  }, []);

  async function loadHistory(page) {
    setHistoryLoading(true);
    try {
      const payload = await fetchDetectionHistory(page);
      startTransition(() => {
        setHistory(payload);
        setHistoryPage(page);
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleUpload(file) {
    setSubmitting(true);
    setError("");

    try {
      const payload = await submitUploadDetection(file);
      startTransition(() => {
        setLatestResult(payload.result);
      });
      loadHistory(1);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUrl(url) {
    setSubmitting(true);
    setError("");

    try {
      const payload = await submitUrlDetection(url);
      startTransition(() => {
        setLatestResult(payload.result);
      });
      loadHistory(1);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <nav className="navbar navbar-expand-lg bg-white border-bottom sticky-top">
        <div className="container">
          <span className="navbar-brand fw-semibold mb-0 h1">AI Media Detector</span>
          <span className="badge rounded-pill text-bg-light">Django + React</span>
        </div>
      </nav>

      <main className="container py-4 py-lg-5">
        <section className="hero-card rounded-5 p-4 p-lg-5 mb-4">
          <div className="row g-4 align-items-center">
            <div className="col-lg-7">
              <span className="badge text-bg-primary-subtle text-primary-emphasis mb-3">
                PythonAnywhere free-plan ready
              </span>
              <h1 className="display-6 fw-semibold mb-3">
                Check whether an image, short video, or public social link looks AI-generated.
              </h1>
              <p className="lead text-secondary mb-0">
                The pipeline stays lightweight by combining upload validation, preview extraction, heuristic scoring,
                and short synchronous CPU-only analysis.
              </p>
            </div>
            <div className="col-lg-5">
              <div className="stats-panel rounded-4 bg-white p-4 shadow-sm">
                <div className="small text-uppercase text-secondary fw-semibold mb-3">Runtime guardrails</div>
                <div className="d-grid gap-2">
                  <div>Images up to 10 MB</div>
                  <div>Videos up to 20 MB</div>
                  <div>Only first 12 seconds sampled</div>
                  <div>YouTube and Facebook public previews</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <AlertMessage message={error} />

        <section className="mb-4">
          <ul className="nav nav-pills gap-2">
            <li className="nav-item">
              <button
                type="button"
                className={`nav-link ${activeTab === "upload" ? "active" : "bg-white text-dark"}`}
                onClick={() => setActiveTab("upload")}
              >
                Upload
              </button>
            </li>
            <li className="nav-item">
              <button
                type="button"
                className={`nav-link ${activeTab === "url" ? "active" : "bg-white text-dark"}`}
                onClick={() => setActiveTab("url")}
              >
                URL
              </button>
            </li>
          </ul>
        </section>

        <section className="row g-4 mb-4">
          <div className="col-lg-7">
            {activeTab === "upload" ? (
              <UploadForm loading={submitting} onSubmit={handleUpload} />
            ) : (
              <UrlForm loading={submitting} onSubmit={handleUrl} />
            )}
          </div>
          <div className="col-lg-5">
            {submitting ? <LoadingState label="Running detection..." /> : <ResultCard result={latestResult} />}
          </div>
        </section>

        <section>
          <HistoryTable
            history={history}
            loading={historyLoading}
            page={historyPage}
            onPageChange={loadHistory}
          />
        </section>
      </main>
    </div>
  );
}
