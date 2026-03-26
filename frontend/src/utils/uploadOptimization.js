function revokeObjectUrl(url) {
  if (url) {
    URL.revokeObjectURL(url);
  }
}

function getNavigatorConnection() {
  if (typeof navigator === "undefined") {
    return null;
  }

  return navigator.connection || navigator.mozConnection || navigator.webkitConnection || null;
}

function detectUploadContext(file) {
  if (typeof navigator === "undefined") {
    return {
      mobileBrowser: false,
      slowConnection: false,
      saveData: false,
      connectionEffectiveType: "",
      networkDownlinkMbps: null,
      deviceMemoryGb: null,
      preferFastAnalysis: false,
    };
  }

  const connection = getNavigatorConnection();
  const connectionEffectiveType = connection?.effectiveType || "";
  const saveData = Boolean(connection?.saveData);
  const networkDownlinkMbps =
    typeof connection?.downlink === "number" && Number.isFinite(connection.downlink) ? connection.downlink : null;
  const deviceMemoryGb =
    typeof navigator.deviceMemory === "number" && Number.isFinite(navigator.deviceMemory)
      ? navigator.deviceMemory
      : null;
  const mobileBrowser = /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent || "");
  const slowConnection =
    saveData || ["slow-2g", "2g", "3g"].includes(connectionEffectiveType) || (networkDownlinkMbps !== null && networkDownlinkMbps < 1.5);
  const preferFastAnalysis =
    slowConnection || (mobileBrowser && file.size > 4 * 1024 * 1024) || (deviceMemoryGb !== null && deviceMemoryGb <= 4);

  return {
    mobileBrowser,
    slowConnection,
    saveData,
    connectionEffectiveType,
    networkDownlinkMbps,
    deviceMemoryGb,
    preferFastAnalysis,
  };
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

function buildClientMetadata(file, optimization = null, context = {}, image = null) {
  const extension = file.name.includes(".") ? `.${file.name.split(".").pop()?.toLowerCase() || ""}` : "";
  const metadata = {
    original_extension: extension,
    original_bytes: file.size,
    original_mime_type: file.type,
    mobile_browser: context.mobileBrowser || undefined,
    slow_connection: context.slowConnection || undefined,
    save_data: context.saveData || undefined,
    prefer_fast_analysis: context.preferFastAnalysis || undefined,
    connection_effective_type: context.connectionEffectiveType || undefined,
    network_downlink_mbps: context.networkDownlinkMbps ?? undefined,
    device_memory_gb: context.deviceMemoryGb ?? undefined,
    original_width: image?.width || undefined,
    original_height: image?.height || undefined,
  };

  if (optimization) {
    metadata.browser_upload_optimized = true;
    metadata.optimized_bytes = optimization.optimizedBytes;
    metadata.optimized_width = optimization.width;
    metadata.optimized_height = optimization.height;
  }

  const hasMeaningfulMetadata = Object.values(metadata).some(
    (value) => value !== undefined && value !== null && value !== "" && value !== false,
  );

  return hasMeaningfulMetadata ? metadata : null;
}

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MOBILE_OPTIMIZATION_TRIGGER_BYTES = 4 * 1024 * 1024;

export async function prepareUploadFile(file) {
  if (!file) {
    return { file, optimization: null, clientMetadata: null };
  }

  const context = detectUploadContext(file);

  if (!file.type.startsWith("image/")) {
    return { file, optimization: null, clientMetadata: buildClientMetadata(file, null, context) };
  }

  const image = await loadImageFromFile(file);
  const maxDimension = context.preferFastAnalysis ? 1440 : 1600;
  const veryLargeResolution = image.width * image.height >= 12_000_000;
  const mobileOptimizationNeeded =
    context.preferFastAnalysis &&
    file.size > MOBILE_OPTIMIZATION_TRIGGER_BYTES &&
    (image.width > maxDimension || image.height > maxDimension || veryLargeResolution);
  const needsResize =
    (file.size > MAX_IMAGE_BYTES || mobileOptimizationNeeded) && (image.width > maxDimension || image.height > maxDimension);
  const needsCompression = file.size > MAX_IMAGE_BYTES || mobileOptimizationNeeded;
  if (!needsResize && !needsCompression) {
    return { file, optimization: null, clientMetadata: buildClientMetadata(file, null, context, image) };
  }

  const scale = Math.min(1, maxDimension / Math.max(image.width, image.height));
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const canvasContext = canvas.getContext("2d", { alpha: true });
  if (!canvasContext) {
    return { file, optimization: null, clientMetadata: null };
  }

  canvasContext.drawImage(image, 0, 0, width, height);
  const keepPng = file.type === "image/png" && hasTransparentPixels(canvasContext, width, height);
  const mimeType = keepPng ? "image/png" : "image/jpeg";
  const quality = keepPng ? undefined : context.preferFastAnalysis ? 0.8 : 0.82;
  const optimizedBlob = await canvasToBlob(canvas, mimeType, quality);

  if (optimizedBlob.size >= file.size * 0.95) {
    return { file, optimization: null, clientMetadata: buildClientMetadata(file, null, context, image) };
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
    clientMetadata: buildClientMetadata(file, optimization, context, image),
  };
}
