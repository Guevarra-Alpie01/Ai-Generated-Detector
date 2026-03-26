function revokeObjectUrl(url) {
  if (url) {
    URL.revokeObjectURL(url);
  }
}

function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      revokeObjectUrl(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      revokeObjectUrl(objectUrl);
      reject(new Error("The selected image could not be prepared for upload."));
    };
    image.src = objectUrl;
  });
}

function canvasToBlob(canvas, mimeType, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
        return;
      }
      reject(new Error("The selected image could not be optimized for upload."));
    }, mimeType, quality);
  });
}

function hasTransparentPixels(context, width, height) {
  const { data } = context.getImageData(0, 0, width, height);
  for (let index = 3; index < data.length; index += 4) {
    if (data[index] < 255) {
      return true;
    }
  }
  return false;
}

function buildOptimizedName(file, mimeType) {
  const stem = file.name.replace(/\.[^.]+$/, "") || "upload";
  const suffix = mimeType === "image/png" ? ".png" : ".jpg";
  return `${stem}${suffix}`;
}

function buildClientMetadata(file, optimization = null) {
  const extension = file.name.includes(".") ? `.${file.name.split(".").pop()?.toLowerCase() || ""}` : "";
  return optimization
    ? {
        browser_upload_optimized: true,
        original_extension: extension,
        original_bytes: file.size,
        original_mime_type: file.type,
        optimized_bytes: optimization.optimizedBytes,
        optimized_width: optimization.width,
        optimized_height: optimization.height,
      }
    : null;
}

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export async function prepareUploadFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    return { file, optimization: null, clientMetadata: null };
  }

  const image = await loadImageFromFile(file);
  const maxDimension = 1600;
  const needsResize = file.size > MAX_IMAGE_BYTES && (image.width > maxDimension || image.height > maxDimension);
  const needsCompression = file.size > MAX_IMAGE_BYTES;
  if (!needsResize && !needsCompression) {
    return { file, optimization: null, clientMetadata: null };
  }

  const scale = Math.min(1, maxDimension / Math.max(image.width, image.height));
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) {
    return { file, optimization: null, clientMetadata: null };
  }

  context.drawImage(image, 0, 0, width, height);
  const keepPng = file.type === "image/png" && hasTransparentPixels(context, width, height);
  const mimeType = keepPng ? "image/png" : "image/jpeg";
  const quality = keepPng ? undefined : 0.82;
  const optimizedBlob = await canvasToBlob(canvas, mimeType, quality);

  if (optimizedBlob.size >= file.size * 0.95) {
    return { file, optimization: null, clientMetadata: null };
  }

  const optimizedFile = new File([optimizedBlob], buildOptimizedName(file, mimeType), {
    type: mimeType,
    lastModified: file.lastModified,
  });

  const optimization = {
    originalBytes: file.size,
    optimizedBytes: optimizedFile.size,
    width,
    height,
  };

  return {
    file: optimizedFile,
    optimization,
    clientMetadata: buildClientMetadata(file, optimization),
  };
}
