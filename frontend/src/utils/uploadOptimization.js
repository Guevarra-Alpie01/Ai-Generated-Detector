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

export async function prepareUploadFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    return { file, optimization: null };
  }

  const image = await loadImageFromFile(file);
  const maxDimension = 1600;
  const needsResize = image.width > maxDimension || image.height > maxDimension;
  const needsCompression = file.size > 1.5 * 1024 * 1024;
  if (!needsResize && !needsCompression) {
    return { file, optimization: null };
  }

  const scale = Math.min(1, maxDimension / Math.max(image.width, image.height));
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) {
    return { file, optimization: null };
  }

  context.drawImage(image, 0, 0, width, height);
  const keepPng = file.type === "image/png" && hasTransparentPixels(context, width, height);
  const mimeType = keepPng ? "image/png" : "image/jpeg";
  const quality = keepPng ? undefined : 0.82;
  const optimizedBlob = await canvasToBlob(canvas, mimeType, quality);

  if (optimizedBlob.size >= file.size * 0.95) {
    return { file, optimization: null };
  }

  const optimizedFile = new File([optimizedBlob], buildOptimizedName(file, mimeType), {
    type: mimeType,
    lastModified: file.lastModified,
  });

  return {
    file: optimizedFile,
    optimization: {
      originalBytes: file.size,
      optimizedBytes: optimizedFile.size,
      width,
      height,
    },
  };
}
