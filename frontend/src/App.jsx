import { startTransition, useEffect, useState } from "react";

import { fetchDetectionHistory, resetClientSessionHistory, submitUploadDetection, submitUrlDetection } from "./api/client";
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

const THEME_STORAGE_KEY = "ai-media-detector-theme";

function getInitialTheme() {
  if (typeof window === "undefined") {
    return "light";
  }

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === "light" || storedTheme === "dark") {
    return storedTheme;
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function ThemeIcon({ theme }) {
  if (theme === "dark") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="theme-icon">
        <path
          d="M12 4.75a.75.75 0 0 1 .75.75v1.25a.75.75 0 0 1-1.5 0V5.5a.75.75 0 0 1 .75-.75Zm0 12.5a.75.75 0 0 1 .75.75v1.25a.75.75 0 0 1-1.5 0V18a.75.75 0 0 1 .75-.75Zm7.25-6a.75.75 0 0 1 0 1.5H18a.75.75 0 0 1 0-1.5h1.25Zm-12.5 0a.75.75 0 0 1 0 1.5H5.5a.75.75 0 0 1 0-1.5h1.25Zm9.028-4.278a.75.75 0 0 1 1.06 0l.884.884a.75.75 0 0 1-1.06 1.06l-.884-.883a.75.75 0 0 1 0-1.061Zm-9.5 9.5a.75.75 0 0 1 1.061 0l.884.884a.75.75 0 1 1-1.06 1.06l-.885-.884a.75.75 0 0 1 0-1.06Zm10.384 1.944a.75.75 0 0 1 1.06-1.06l.884.883a.75.75 0 1 1-1.06 1.06l-.884-.883Zm-9.5-9.5a.75.75 0 0 1 1.06-1.06l.885.883a.75.75 0 0 1-1.06 1.06l-.885-.883ZM12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="theme-icon">
      <path
        d="M21 14.8A8.8 8.8 0 0 1 9.2 3a.7.7 0 0 0-.9-.9A10.2 10.2 0 1 0 21.9 15.7a.7.7 0 0 0-.9-.9Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("upload");
  const [latestResult, setLatestResult] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState(EMPTY_HISTORY);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyPage, setHistoryPage] = useState(1);
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    void loadHistory(1);
  }, []);

  useEffect(() => {
    function handlePageHide() {
      void resetClientSessionHistory();
    }

    window.addEventListener("pagehide", handlePageHide);
    return () => {
      window.removeEventListener("pagehide", handlePageHide);
    };
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-bs-theme", theme);
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

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

  async function handleUpload(preparedUpload) {
    setSubmitting(true);
    setError("");

    try {
      const payload = await submitUploadDetection(preparedUpload.file, preparedUpload.clientMetadata);
      startTransition(() => {
        setLatestResult(payload.result);
      });
      void loadHistory(1);
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
      void loadHistory(1);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  function toggleTheme() {
    setTheme((currentTheme) => (currentTheme === "dark" ? "light" : "dark"));
  }

  return (
    <div className="app-shell">
      <nav className="topbar">
        <div className="container topbar-inner">
          <div className="topbar-brand">
            <span className="topbar-title">AI Media Detector</span>
          </div>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            <ThemeIcon theme={theme} />
          </button>
        </div>
      </nav>

      <main className="container py-4 py-lg-5">
        <section className="analysis-stage mx-auto">
          <div className="analysis-copy text-center">
            <span className="analysis-kicker">Fast media screening</span>
            <h1 className="analysis-title">Upload a file or paste a public link to check it instantly.</h1>
            <p className="analysis-subtitle">
              The detector keeps the main action front and center, then shows the result as soon as analysis finishes.
            </p>
          </div>

          <AlertMessage message={error} />

          <div className="analysis-workspace panel-card">
            <div className="analysis-column">
              <div className="mode-switch" role="tablist" aria-label="Input mode">
                <button
                  type="button"
                  className={`mode-switch-button ${activeTab === "upload" ? "active" : ""}`}
                  onClick={() => setActiveTab("upload")}
                  aria-pressed={activeTab === "upload"}
                >
                  Upload
                </button>
                <button
                  type="button"
                  className={`mode-switch-button ${activeTab === "url" ? "active" : ""}`}
                  onClick={() => setActiveTab("url")}
                  aria-pressed={activeTab === "url"}
                >
                  URL
                </button>
              </div>

              {activeTab === "upload" ? (
                <UploadForm loading={submitting} onSubmit={handleUpload} />
              ) : (
                <UrlForm loading={submitting} onSubmit={handleUrl} />
              )}
            </div>

            <div className="analysis-column">
              {submitting ? (
                <LoadingState
                  label={activeTab === "upload" ? "Analyzing upload" : "Analyzing link"}
                  detail="This usually finishes in a few seconds, but larger uploads on phones can take a bit longer."
                />
              ) : (
                <ResultCard result={latestResult} />
              )}
            </div>
          </div>
        </section>

        <section className="history-section mx-auto">
          <HistoryTable history={history} loading={historyLoading} page={historyPage} onPageChange={loadHistory} />
        </section>

        <section className="system-footer mx-auto">
          <footer className="footer-panel">
            <div className="footer-column">
              <div className="result-eyebrow">System Stack</div>
              <h2 className="footer-title">Built for fast, lightweight AI media screening.</h2>
              <p className="footer-copy">
                Powered by Python, Django, Django REST Framework, React, Bootstrap, and SQLite.
              </p>
              <div className="footer-stack-list">
                <span className="footer-stack-pill">Python</span>
                <span className="footer-stack-pill">Django</span>
                <span className="footer-stack-pill">DRF</span>
                <span className="footer-stack-pill">React</span>
                <span className="footer-stack-pill">Bootstrap</span>
                <span className="footer-stack-pill">SQLite</span>
              </div>
            </div>

            <div className="footer-column">
              <div className="result-eyebrow">Developer</div>
              <h2 className="footer-title">Alpie Guevarra</h2>
              <p className="footer-copy mb-0">
                Aspiring full stack developer, web developer, and software engineer building practical, responsive
                systems with clean user-focused design.
              </p>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}
