export default function LoadingState({ label = "Loading..." }) {
  return (
    <div className="d-flex align-items-center gap-3 rounded-4 border bg-white p-4 shadow-sm">
      <div className="spinner-border text-primary" role="status" aria-hidden="true" />
      <span className="text-secondary">{label}</span>
    </div>
  );
}
