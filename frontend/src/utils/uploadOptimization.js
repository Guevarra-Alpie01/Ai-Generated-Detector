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

async function readStorageEstimate() {
  if (typeof navigator === "undefined" || !navigator.storage?.estimate) {
    return {
      quotaBytes: null,
      usageBytes: null,
      availableBytes: null,
      lowStorageDevice: false,
    };
  }

  try {
    const { quota, usage } = await navigator.storage.estimate();
    const quotaBytes = typeof quota === "number" && Number.isFinite(quota) ? quota : null;
    const usageBytes = typeof usage === "number" && Number.isFinite(usage) ? usage : null;
    const availableBytes =
      quotaBytes !== null && usageBytes !== null ? Math.max(0, quotaBytes - usageBytes) : null;
    const lowStorageDevice = availableBytes !== null && availableBytes < 256 * 1024 * 1024;

    return {
      quotaBytes,
      usageBytes,
      availableBytes,
      lowStorageDevice,
    };
  } catch {
    return {
      quotaBytes: null,
      usageBytes: null,
      availableBytes: null,
      lowStorageDevice: false,
    };
  }
}

async function detectUploadContext(file) {
  if (typeof navigator === "undefined") {
    return {
      mobileBrowser: false,
      slowConnection: false,
      saveData: false,
      connectionEffectiveType: "",
      networkDownlinkMbps: null,
      deviceMemoryGb: null,
      lowStorageDevice: false,
      storageQuotaBytes: null,
      storageUsageBytes: null,
      storageAvailableBytes: null,
      preferFastAnalysis: false,
    };
  }

  const connection = getNavigatorConnection();
  const storage = await readStorageEstimate();
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
    slowConnection ||
    storage.lowStorageDevice ||
    (mobileBrowser && file.size > 4 * 1024 * 1024) ||
    (deviceMemoryGb !== null && deviceMemoryGb <= 4);

  return {
    mobileBrowser,
    slowConnection,
    saveData,
    connectionEffectiveType,
    networkDownlinkMbps,
    deviceMemoryGb,
    lowStorageDevice: storage.lowStorageDevice,
    storageQuotaBytes: storage.quotaBytes,
    storageUsageBytes: storage.usageBytes,
    storageAvailableBytes: storage.availableBytes,
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
    low_storage_device: context.lowStorageDevice || undefined,
    storage_quota_bytes: context.storageQuotaBytes ?? undefined,
    storage_usage_bytes: context.storageUsageBytes ?? undefined,
    storage_available_bytes: context.storageAvailableBytes ?? undefined,
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
const MOBILE_OPTIMIZATION_TRIGGER_BYTES = 2.5 * 1024 * 1024;

function buildPreparationMessages(file, context, optimization = null) {
  const messages = [];

  if (context.slowConnection) {
    messages.push("Slow connection detected. Mobile-friendly upload mode is on to improve the chance that analysis finishes.");
  }

  if (context.lowStorageDevice) {
    messages.push("Limited free storage was detected on this device, so the upload is prepared in a lighter format when possible.");
  }

  if (context.preferFastAnalysis && file.type.startsWith("video/")) {
    messages.push("Large mobile videos use a faster analysis path. Shorter clips and Wi-Fi are still the most reliable option.");
  }

  if (optimization) {
    messages.push("If the network drops during upload, retrying the same file can still reuse the server's recent-result cache.");
  }

  return messages;
}

function buildOptimizationCandidates(context, image) {
  const primaryDimension = context.preferFastAnalysis ? 1440 : 1600;
  const candidates = [
    { maxDimension: primaryDimension, quality: context.preferFastAnalysis ? 0.8 : 0.82 },
  ];

  if (context.preferFastAnalysis || context.lowStorageDevice) {
    candidates.push({ maxDimension: 1280, quality: 0.72 });
    candidates.push({ maxDimension: 1080, quality: 0.64 });
  }

  if (context.slowConnection) {
    candidates.push({ maxDimension: 960, quality: 0.58 });
  }

  return candidates.filter(
    (candidate, index, allCandidates) =>
      index ===
      allCandidates.findIndex(
        (existingCandidate) =>
          existingCandidate.maxDimension === candidate.maxDimension &&
          existingCandidate.quality === candidate.quality,
      ),
  );
}

function resolveImageTargetBytes(file, context) {
  if (context.slowConnection || context.lowStorageDevice) {
    return Math.min(MAX_IMAGE_BYTES, 2.25 * 1024 * 1024);
  }

  if (context.preferFastAnalysis) {
    return Math.min(MAX_IMAGE_BYTES, 3.5 * 1024 * 1024);
  }

  return MAX_IMAGE_BYTES;
}

async function renderOptimizedImageCandidate(image, file, candidate) {
  const scale = Math.min(1, candidate.maxDimension / Math.max(image.width, image.height));
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const canvasContext = canvas.getContext("2d", { alpha: true });
  if (!canvasContext) {
    return null;
  }

  canvasContext.drawImage(image, 0, 0, width, height);
  const keepPng = file.type === "image/png" && hasTransparentPixels(canvasContext, width, height);
  const mimeType = keepPng ? "image/png" : "image/jpeg";
  const quality = keepPng ? undefined : candidate.quality;
  const optimizedBlob = await canvasToBlob(canvas, mimeType, quality);

  return {
    blob: optimizedBlob,
    width,
    height,
    mimeType,
  };
}

export async function prepareUploadFile(file) {
  if (!file) {
    return { file, optimization: null, clientMetadata: null, feedbackMessages: [] };
  }

  const context = await detectUploadContext(file);

  if (!file.type.startsWith("image/")) {
    return {
      file,
      optimization: null,
      clientMetadata: buildClientMetadata(file, null, context),
      feedbackMessages: buildPreparationMessages(file, context),
    };
  }

  const image = await loadImageFromFile(file);
  const longestDimension = Math.max(image.width, image.height);
  const maxDimension = context.preferFastAnalysis ? 1440 : 1600;
  const veryLargeResolution = image.width * image.height >= 10_000_000;
  const mobileOptimizationNeeded =
    context.preferFastAnalysis &&
    file.size > MOBILE_OPTIMIZATION_TRIGGER_BYTES &&
    (image.width > maxDimension || image.height > maxDimension || veryLargeResolution || longestDimension > 2000);
  const needsResize =
    (file.size > MAX_IMAGE_BYTES || mobileOptimizationNeeded) && (image.width > maxDimension || image.height > maxDimension);
  const needsCompression =
    file.size > MAX_IMAGE_BYTES ||
    mobileOptimizationNeeded ||
    ((context.slowConnection || context.lowStorageDevice) && file.size > 1.8 * 1024 * 1024);
  if (!needsResize && !needsCompression) {
    return {
      file,
      optimization: null,
      clientMetadata: buildClientMetadata(file, null, context, image),
      feedbackMessages: buildPreparationMessages(file, context),
    };
  }

  const targetBytes = resolveImageTargetBytes(file, context);
  const candidates = buildOptimizationCandidates(context, image);
  let bestCandidate = null;

  for (const candidate of candidates) {
    const renderedCandidate = await renderOptimizedImageCandidate(image, file, candidate);
    if (!renderedCandidate) {
      continue;
    }

    if (!bestCandidate || renderedCandidate.blob.size < bestCandidate.blob.size) {
      bestCandidate = renderedCandidate;
    }

    if (renderedCandidate.blob.size <= targetBytes) {
      break;
    }
  }

  if (!bestCandidate || bestCandidate.blob.size >= file.size * 0.97) {
    return {
      file,
      optimization: null,
      clientMetadata: buildClientMetadata(file, null, context, image),
      feedbackMessages: buildPreparationMessages(file, context),
    };
  }

  const optimizedFile = new File([bestCandidate.blob], buildOptimizedName(file, bestCandidate.mimeType), {
    type: bestCandidate.mimeType,
    lastModified: file.lastModified,
  });

  const optimization = {
    originalBytes: file.size,
    optimizedBytes: optimizedFile.size,
    width: bestCandidate.width,
    height: bestCandidate.height,
  };

  return {
    file: optimizedFile,
    optimization,
    clientMetadata: buildClientMetadata(file, optimization, context, image),
    feedbackMessages: buildPreparationMessages(file, context, optimization),
  };
}
