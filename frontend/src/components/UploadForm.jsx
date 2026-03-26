import { useEffect, useState } from "react";

import AlertMessage from "./AlertMessage";
import { prepareUploadFile } from "../utils/uploadOptimization";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_VIDEO_BYTES = 20 * 1024 * 1024;

function validateFile(file) {
  const extension = file.name.split(".").pop()?.toLowerCase() || "";

  if (["jpg", "jpeg", "png"].includes(extension) && file.size > MAX_IMAGE_BYTES) {
    return "Images must be 10 MB or smaller.";
  }

  if (extension === "mp4" && file.size > MAX_VIDEO_BYTES) {
    return "Videos must be 20 MB or smaller.";
  }

  if (!["jpg", "jpeg", "png", "mp4"].includes(extension)) {
    return "Supported files: JPG, JPEG, PNG, MP4.";
  }

  return "";
}

export default function UploadForm({ loading, onSubmit }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");
  const [optimizationNote, setOptimizationNote] = useState("");

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  function handleFileChange(event) {
    const nextFile = event.target.files?.[0] || null;
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl("");
    }

    setFile(nextFile);
    if (!nextFile) {
      setError("");
      setOptimizationNote("");
      return;
    }

    const validationError = validateFile(nextFile);
    setError(validationError);

    if (nextFile.type.startsWith("image/")) {
      setPreviewUrl(URL.createObjectURL(nextFile));
    }
  }

  function formatMegabytes(bytes) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!file) {
      setError("Choose an image or MP4 file first.");
      return;
    }

    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError("");
    try {
      const preparedUpload = await prepareUploadFile(file);
      if (preparedUpload.optimization) {
        setOptimizationNote(
          `Optimized from ${formatMegabytes(preparedUpload.optimization.originalBytes)} to ${formatMegabytes(preparedUpload.optimization.optimizedBytes)} before upload.`,
        );
      } else {
        setOptimizationNote("");
      }
      await onSubmit(preparedUpload.file);
    } catch (submitError) {
      setError(submitError.message || "The upload could not be prepared.");
    }
  }

  return (
    <section className="form-panel">
      <div className="form-panel-header">
        <div>
          <h2 className="form-panel-title">Upload media</h2>
          <p className="form-panel-copy">JPG, PNG, JPEG, or short MP4.</p>
        </div>
        <span className="form-chip">10 MB image / 20 MB video</span>
      </div>

      <AlertMessage message={error} />
      <AlertMessage variant="info" message={optimizationNote} />

      <form onSubmit={handleSubmit} className="d-grid gap-3">
        <div className="upload-dropzone">
          <label htmlFor="media-upload" className="upload-dropzone-label">
            <span className="upload-dropzone-title">{file ? "File ready to analyze" : "Choose a file"}</span>
            <span className="upload-dropzone-copy">
              {file ? file.name : "Drag one in or browse from your device."}
            </span>
          </label>
          <input
            id="media-upload"
            className="form-control form-control-lg"
            type="file"
            accept=".jpg,.jpeg,.png,.mp4"
            onChange={handleFileChange}
          />
          <div className="form-note">Original images are preserved unless optimization is needed to fit upload limits.</div>
        </div>

        {previewUrl && (
          <div className="preview-panel">
            <img src={previewUrl} alt="Preview" className="img-fluid rounded-4" />
          </div>
        )}

        <button type="submit" className="btn btn-primary btn-lg action-button" disabled={loading}>
          {loading ? "Analyzing..." : "Analyze upload"}
        </button>
      </form>
    </section>
  );
}
