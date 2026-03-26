function clampPercentage(value) {
  const numeric = Number(value || 0);
  const normalized = numeric > 1 ? numeric / 100 : numeric;
  return Math.max(0, Math.min(1, normalized));
}

function formatPercentage(value) {
  return `${Math.round(clampPercentage(value) * 100)}%`;
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

function getDisplayResult(result) {
  const aiProbability = getAiProbability(result);
  const label = aiProbability >= 0.5 ? "Likely AI-generated" : "Likely real";
  const badgeClass = aiProbability >= 0.5 ? "text-bg-danger" : "text-bg-success";

  return {
    aiProbability,
    realProbability: 1 - aiProbability,
    label,
    badgeClass,
  };
}

function formatCreatedAt(value) {
  if (!value) {
    return "Just now";
  }
  return new Date(value).toLocaleString();
}

function MetricCard({ label, value, tone }) {
  return (
    <div className="minimal-result-metric">
      <div className="minimal-result-metric-label">{label}</div>
      <div className="minimal-result-metric-value">{value}</div>
      <div className={`metric-bar ${tone === "ai" ? "metric-bar-ai" : "metric-bar-real"}`}>
        <span style={{ width: value }} />
      </div>
    </div>
  );
}

export default function ResultCard({ result }) {
  if (!result) {
    return (
      <section className="result-shell result-placeholder">
        <div className="result-eyebrow">Awaiting analysis</div>
        <h2 className="result-title">Results appear here as soon as the scan finishes.</h2>
        <p className="result-copy">Run an upload or URL check to see the result instantly.</p>
        <div className="result-disclaimer">
          AI analysis can still make mistakes and should be treated as a helpful signal, not final proof.
        </div>
      </section>
    );
  }

  const source = result.original_filename || result.source_url || result.source_type;
  const displayResult = getDisplayResult(result);

  return (
    <section className="result-shell minimal-result-shell">
      <div className="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
        <div>
          <div className="result-eyebrow">Latest result</div>
          <h2 className="result-title">{source}</h2>
          <p className="result-copy mb-0">Completed {formatCreatedAt(result.created_at)}</p>
        </div>
        <span className={`badge ${displayResult.badgeClass} result-badge`}>{displayResult.label}</span>
      </div>

      <div className="minimal-result-grid">
        <MetricCard label="Likely real" value={formatPercentage(displayResult.realProbability)} tone="real" />
        <MetricCard label="Likely AI-generated" value={formatPercentage(displayResult.aiProbability)} tone="ai" />
      </div>
    </section>
  );
}
