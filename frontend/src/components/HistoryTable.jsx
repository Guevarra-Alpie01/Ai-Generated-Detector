export default function HistoryTable({ history, loading, page, onPageChange }) {
  return (
    <div className="card border-0 shadow-sm">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <div>
            <h2 className="h5 mb-1">Detection History</h2>
            <p className="text-secondary mb-0">Recent analyses saved in SQLite.</p>
          </div>
          <span className="badge text-bg-light">{history.count || 0} total</span>
        </div>

        <div className="table-responsive">
          <table className="table align-middle">
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
                  <td className="history-source-cell">
                    {item.original_filename || item.source_url || "Uploaded media"}
                  </td>
                  <td className="text-capitalize">{item.source_type}</td>
                  <td>
                    <span
                      className={`badge ${
                        item.result_label === "AI-generated" ? "text-bg-danger" : "text-bg-success"
                      }`}
                    >
                      {item.result_label}
                    </span>
                  </td>
                  <td>{Number(item.confidence_score).toFixed(2)}%</td>
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
    </div>
  );
}
