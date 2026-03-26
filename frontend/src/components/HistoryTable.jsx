function formatPercentage(value) {
  const numeric = Number(value || 0);
  const normalized = numeric > 1 ? numeric / 100 : numeric;
  return `${(Math.max(0, Math.min(1, normalized)) * 100).toFixed(0)}%`;
}

function labelClass(label) {
  if (label === "AI-generated") {
    return "text-bg-danger";
  }
  if (label === "Uncertain") {
    return "text-bg-warning";
  }
  return "text-bg-success";
}

export default function HistoryTable({ history, loading, page, onPageChange }) {
  return (
    <div className="panel-card history-card">
      <div className="d-flex justify-content-between align-items-center mb-3 gap-3 flex-wrap">
        <div>
          <h2 className="h4 mb-1">Detection history</h2>
          <p className="text-secondary mb-0">Recent analyses saved in SQLite.</p>
        </div>
        <span className="form-chip">{history.count || 0} total</span>
      </div>

      <div className="table-responsive">
        <table className="table align-middle history-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Type</th>
              <th>Result</th>
              <th>Confidence</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {!loading && history.results.length === 0 && (
              <tr>
                <td colSpan="5" className="text-center text-secondary py-4">
                  No detections yet.
                </td>
              </tr>
            )}

            {history.results.map((item) => (
              <tr key={item.id}>
                <td className="history-source-cell">{item.original_filename || item.source_url || "Uploaded media"}</td>
                <td className="text-capitalize">{item.source_type}</td>
                <td>
                  <span className={`badge ${labelClass(item.result_label)}`}>{item.result_label}</span>
                </td>
                <td>{formatPercentage(item.confidence_score)}</td>
                <td>{new Date(item.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="d-flex justify-content-between align-items-center mt-3">
        <button
          type="button"
          className="btn btn-outline-secondary"
          onClick={() => onPageChange(page - 1)}
          disabled={loading || !history.previous || page <= 1}
        >
          Previous
        </button>
        <span className="small text-secondary">Page {page}</span>
        <button
          type="button"
          className="btn btn-outline-secondary"
          onClick={() => onPageChange(page + 1)}
          disabled={loading || !history.next}
        >
          Next
        </button>
      </div>
    </div>
  );
}
