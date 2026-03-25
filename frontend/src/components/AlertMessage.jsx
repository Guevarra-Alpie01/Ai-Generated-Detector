export default function AlertMessage({ variant = "danger", message }) {
  if (!message) {
    return null;
  }

  return (
    <div className={`alert alert-${variant}`} role="alert">
      {message}
    </div>
  );
}
