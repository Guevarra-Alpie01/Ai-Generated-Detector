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
          `Optimized image upload from ${formatMegabytes(
            preparedUpload.optimization.originalBytes,
          )} to ${formatMegabytes(preparedUpload.optimization.optimizedBytes)} for a faster mobile upload.`,
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
    <div className="card border-0 shadow-sm h-100">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between align-items-start mb-3">
          <div>
            <h2 className="h5 mb-1">Upload Media</h2>
            <p className="text-secondary mb-0">JPG, JPEG, PNG, or short MP4 clips only.</p>
          </div>
          <span className="badge text-bg-light">CPU-safe</span>
        </div>

        <AlertMessage message={error} />
        <AlertMessage variant="info" message={optimizationNote} />

        <form onSubmit={handleSubmit} className="d-grid gap-3">
          <div className="upload-dropzone rounded-4 border border-2 border-dashed p-4 bg-light-subtle">
            <label htmlFor="media-upload" className="form-label fw-semibold">
              Select a file
            </label>
            <input
              id="media-upload"
              className="form-control"
              type="file"
              accept=".jpg,.jpeg,.png,.mp4"
              onChange={handleFileChange}
            />
            <div className="form-text mt-2">
              Images max 10 MB. Videos max 20 MB. Large photos are shrunk in the browser first to help slower mobile
              connections.
            </div>
          </div>

          {previewUrl && (
            <div className="rounded-4 overflow-hidden border bg-white p-2">
              <img src={previewUrl} alt="Preview" className="img-fluid rounded-3" />
            </div>
          )}

          <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
            {loading ? "Analyzing..." : "Analyze Upload"}
          </button>
        </form>
      </div>
    </div>
  );
}
