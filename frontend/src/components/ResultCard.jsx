function confidenceClass(label) {
  if (label === "AI-generated") {
    return "bg-danger";
  }
  if (label === "Uncertain") {
    return "bg-warning text-dark";
  }
  return "bg-success";
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

function formatConfidence(value) {
  const numeric = Number(value || 0);
  const normalized = numeric > 1 ? numeric / 100 : numeric;
  return `${(Math.max(0, Math.min(1, normalized)) * 100).toFixed(0)}%`;
}

export default function ResultCard({ result }) {
  if (!result) {
    return (
      <div className="card border-0 shadow-sm">
        <div className="card-body p-4">
          <h2 className="h5 mb-2">Latest Result</h2>
          <p className="text-secondary mb-0">Run an upload or URL analysis to see the detection summary here.</p>
        </div>
      </div>
    );
  }

  const source = result.original_filename || result.source_url || result.source_type;
  const providersUsed = Array.isArray(result.providers_used) ? result.providers_used : [];
  const externalProviderUsed = providersUsed.some((provider) => provider !== "local");
  const audioSummary = result.audio_summary;
  const audioReason = audioSummary?.reason;
  const audioBadgeLabel = result.audio_analysis_used
    ? "Audio analyzed"
    : audioReason === "preview_only_url"
      ? "Preview image only"
      : audioReason === "ffmpeg_unavailable"
        ? "Audio unavailable"
        : audioReason === "no_audio_stream"
          ? "No audio stream"
          : "Audio skipped";
  const audioBadgeClass = result.audio_analysis_used ? "text-bg-primary" : "text-bg-secondary";

  return (
    <div className="card border-0 shadow-sm">
      <div className="card-body p-4">
        <div className="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-3">
          <div>
            <h2 className="h5 mb-1">Latest Result</h2>
            <p className="text-secondary mb-0">{source}</p>
          </div>
          <span className={`badge ${badgeClass(result.result_label)} px-3 py-2`}>{result.result_label}</span>
        </div>

        <div className="d-flex flex-wrap gap-2 mb-3">
          {result.cached_result && <span className="badge text-bg-info">Recent cache used</span>}
          {externalProviderUsed && <span className="badge text-bg-primary">External provider used</span>}
          {result.fallback_used && <span className="badge text-bg-secondary">Local fallback used</span>}
          {result.result_label === "Uncertain" && <span className="badge text-bg-warning">Uncertain result</span>}
        </div>

        <div className="mb-3">
          <div className="d-flex justify-content-between mb-2">
            <span className="fw-semibold">Confidence</span>
            <span>{formatConfidence(result.confidence_score)}</span>
          </div>
          <div className="progress result-progress" role="progressbar" aria-label="Confidence score">
            <div
              className={`progress-bar ${confidenceClass(result.result_label)}`}
              style={{ width: formatConfidence(result.confidence_score) }}
            />
          </div>
        </div>

        <p className="mb-3">{result.details}</p>

        <div className="row g-3">
          <div className="col-md-6">
            <div className="rounded-4 bg-light p-3 h-100">
              <div className="small text-uppercase text-secondary fw-semibold mb-2">Source</div>
              <div className="fw-semibold text-capitalize">{result.source_type}</div>
              <div className="small text-secondary mt-2">
                Providers: {providersUsed.length > 0 ? providersUsed.join(", ") : "None"}
              </div>
              {result.source_url && (
                <a href={result.source_url} target="_blank" rel="noreferrer" className="small">
                  Open source link
                </a>
              )}
            </div>
          </div>
          <div className="col-md-6">
            <div className="rounded-4 bg-light p-3 h-100">
              <div className="small text-uppercase text-secondary fw-semibold mb-2">Breakdown</div>
              <div className="small">
                Combined AI score: {Number(result.score_breakdown?.ai_score || 0).toFixed(2)}
              </div>
              {result.score_breakdown?.local?.artifact_score !== undefined && (
                <div className="small">
                  Local artifact score: {Number(result.score_breakdown?.local?.artifact_score || 0).toFixed(2)}
                </div>
              )}
              {result.score_breakdown?.local?.frequency_score !== undefined && (
                <div className="small">
                  Local frequency score: {Number(result.score_breakdown?.local?.frequency_score || 0).toFixed(2)}
                </div>
              )}
              {result.score_breakdown?.local?.metadata_score !== undefined && (
                <div className="small">
                  Local metadata score: {Number(result.score_breakdown?.local?.metadata_score || 0).toFixed(2)}
                </div>
              )}
              {result.score_breakdown?.audio_score !== null && result.score_breakdown?.audio_score !== undefined && (
                <div className="small">
                  Audio score: {Number(result.score_breakdown?.audio_score || 0).toFixed(2)}
                </div>
              )}
            </div>
          </div>
        </div>

        {Array.isArray(result.signals) && result.signals.length > 0 && (
          <div className="rounded-4 bg-light p-3 mt-3">
            <div className="small text-uppercase text-secondary fw-semibold mb-2">Signals</div>
            <ul className="small mb-0 ps-3">
              {result.signals.slice(0, 4).map((signal) => (
                <li key={signal}>{signal}</li>
              ))}
            </ul>
          </div>
        )}

        {audioSummary && (
          <div className="rounded-4 bg-light p-3 mt-3">
            <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
              <div className="small text-uppercase text-secondary fw-semibold">Audio</div>
              <span className={`badge ${audioBadgeClass}`}>{audioBadgeLabel}</span>
            </div>
            <p className="small mb-2">{audioSummary.summary || "No usable audio detected."}</p>
            {Array.isArray(audioSummary.signals) && audioSummary.signals.length > 0 && (
              <ul className="small mb-2 ps-3">
                {audioSummary.signals.map((signal) => (
                  <li key={signal}>{signal}</li>
                ))}
              </ul>
            )}
            {audioSummary.audio_score !== null && audioSummary.audio_score !== undefined && (
              <div className="small text-secondary">
                Audio evidence score: {Number(audioSummary.audio_score).toFixed(2)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
