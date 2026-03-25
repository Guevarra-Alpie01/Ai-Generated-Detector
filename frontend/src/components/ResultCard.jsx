function confidenceClass(label) {
  return label === "AI-generated" ? "bg-danger" : "bg-success";
}

function badgeClass(label) {
  return label === "AI-generated" ? "text-bg-danger" : "text-bg-success";
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
  const audioSummary = result.audio_summary;

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

        <div className="mb-3">
          <div className="d-flex justify-content-between mb-2">
            <span className="fw-semibold">Confidence</span>
            <span>{Number(result.confidence_score).toFixed(2)}%</span>
          </div>
          <div className="progress result-progress" role="progressbar" aria-label="Confidence score">
            <div
              className={`progress-bar ${confidenceClass(result.result_label)}`}
              style={{ width: `${Number(result.confidence_score)}%` }}
            />
          </div>
        </div>

        <p className="mb-3">{result.details}</p>

        <div className="row g-3">
          <div className="col-md-6">
            <div className="rounded-4 bg-light p-3 h-100">
              <div className="small text-uppercase text-secondary fw-semibold mb-2">Source</div>
              <div className="fw-semibold text-capitalize">{result.source_type}</div>
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
                AI probability: {Number(result.score_breakdown?.ai_probability || 0).toFixed(2)}
              </div>
              <div className="small">
                Artifact score: {Number(result.score_breakdown?.artifact_score || 0).toFixed(2)}
              </div>
              <div className="small">
                Metadata score: {Number(result.score_breakdown?.metadata_score || 0).toFixed(2)}
              </div>
              {result.score_breakdown?.audio_score !== null && result.score_breakdown?.audio_score !== undefined && (
                <div className="small">
                  Audio score: {Number(result.score_breakdown?.audio_score || 0).toFixed(2)}
                </div>
              )}
            </div>
          </div>
        </div>

        {audioSummary && (
          <div className="rounded-4 bg-light p-3 mt-3">
            <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
              <div className="small text-uppercase text-secondary fw-semibold">Audio</div>
              <span className={`badge ${result.audio_analysis_used ? "text-bg-primary" : "text-bg-secondary"}`}>
                {result.audio_analysis_used ? "Audio analyzed" : "Audio skipped"}
              </span>
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
