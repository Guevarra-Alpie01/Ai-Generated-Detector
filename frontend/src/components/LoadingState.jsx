export default function LoadingState({ label = "Analyzing", detail = "Please wait." }) {
  return (
    <section className="result-shell loading-shell" aria-live="polite">
      <div className="analysis-spinner" aria-hidden="true" />
      <div className="loading-label">{label}</div>
      <p className="loading-copy mb-0">{detail}</p>
    </section>
  );
}
