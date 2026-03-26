function clampPercentage(value) {
  const numeric = Number(value || 0);
  const normalized = numeric > 1 ? numeric / 100 : numeric;
  return Math.max(0, Math.min(1, normalized));
}

function formatPercentage(value) {
  return `${Math.round(clampPercentage(value) * 100)}%`;
}

function badgeClass(label) {
  if (label === "AI-generated") {
    return "text-bg-danger";
  }
  if (label === "Uncertain") {
    return "text-bg-warning";
  }
  return "text-bg-success";
}

function metricToneClass(type) {
  if (type === "ai") {
    return "metric-bar metric-bar-ai";
  }
  return "metric-bar metric-bar-real";
}

function getAiProbability(result) {
  const aiScore = Number(result?.score_breakdown?.ai_score);
  if (Number.isFinite(aiScore)) {
    return clampPercentage(aiScore);
  }

  const confidence = clampPercentage(result?.confidence_score);
  if (result?.result_label === "AI-generated") {
    return confidence;
  }
  if (result?.result_label === "Likely real") {
    return 1 - confidence;
  }
  return 0.5;
}

function formatCreatedAt(value) {
  if (!value) {
    return "Just now";
  }
  return new Date(value).toLocaleString();
}

export default function ResultCard({ result }) {
  if (!result) {
    return (
      <section className="result-shell result-placeholder">
        <div className="result-eyebrow">Awaiting analysis</div>
        <h2 className="result-title">Results appear here as soon as the scan finishes.</h2>
        <p className="result-copy mb-0">Run an upload or URL check to see the real-vs-AI breakdown instantly.</p>
      </section>
    );
  }

  const source = result.original_filename || result.source_url || result.source_type;
  const aiProbability = getAiProbability(result);
  const realProbability = 1 - aiProbability;
  const confidence = clampPercentage(result.confidence_score);
  const providersUsed = Array.isArray(result.providers_used) ? result.providers_used : [];
  const signalPreview = Array.isArray(result.signals) ? result.signals.slice(0, 3) : [];

  return (
    <section className="result-shell">
      <div className="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
        <div>
          <div className="result-eyebrow">Latest result</div>
          <h2 className="result-title">{source}</h2>
          <p className="result-copy mb-0">Completed {formatCreatedAt(result.created_at)}</p>
        </div>
        <span className={`badge ${badgeClass(result.result_label)} result-badge`}>{result.result_label}</span>
      </div>

      <div className="result-score-grid">
        <div className="result-metric-card">
          <div className="metric-label">Likelihood of being real</div>
          <div className="metric-value">{formatPercentage(realProbability)}</div>
          <div className={metricToneClass("real")}>
            <span style={{ width: formatPercentage(realProbability) }} />
          </div>
        </div>
        <div className="result-metric-card">
          <div className="metric-label">Likelihood of being AI-generated</div>
          <div className="metric-value">{formatPercentage(aiProbability)}</div>
          <div className={metricToneClass("ai")}>
            <span style={{ width: formatPercentage(aiProbability) }} />
          </div>
        </div>
      </div>

      <div className="result-meta-grid">
        <div className="result-meta-card">
          <div className="meta-label">Decision confidence</div>
          <div className="meta-value">{formatPercentage(confidence)}</div>
        </div>
        <div className="result-meta-card">
          <div className="meta-label">Source type</div>
          <div className="meta-value text-capitalize">{result.source_type}</div>
        </div>
        <div className="result-meta-card">
          <div className="meta-label">Providers used</div>
          <div className="meta-value">{providersUsed.length > 0 ? providersUsed.join(", ") : "Local only"}</div>
        </div>
      </div>

      <p className="result-summary">{result.details}</p>

      {signalPreview.length > 0 && (
        <div className="signal-list">
          {signalPreview.map((signal) => (
            <div className="signal-pill" key={signal}>
              {signal}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
