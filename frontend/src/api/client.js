const CLIENT_SESSION_STORAGE_KEY = "ai-media-detector-client-session";

function timeoutErrorMessage(kind, timeoutMs) {
  const seconds = Math.round(timeoutMs / 1000);
  return `${kind} took longer than ${seconds} seconds. Large uploads on mobile data may need more time, so try again or use a smaller file if this keeps happening.`;
}

function resolveConnectionInfo() {
  if (typeof navigator === "undefined") {
    return null;
  }

  return navigator.connection || navigator.mozConnection || navigator.webkitConnection || null;
}

function buildUploadTimeoutMs(file, clientMetadata = null) {
  const isVideo = file.type.startsWith("video/");
  const fileSizeMb = Math.max(1, file.size / (1024 * 1024));
  const connection = resolveConnectionInfo();
  const effectiveType = clientMetadata?.connection_effective_type || connection?.effectiveType || "";
  const saveData = Boolean(clientMetadata?.save_data || connection?.saveData);
  const slowConnection = Boolean(clientMetadata?.slow_connection);

  let timeoutMs = isVideo ? 120000 : 75000;
  timeoutMs += Math.round(fileSizeMb * (isVideo ? 9000 : 7000));

  if (saveData || slowConnection || effectiveType === "slow-2g" || effectiveType === "2g") {
    timeoutMs += isVideo ? 120000 : 90000;
  } else if (effectiveType === "3g") {
    timeoutMs += isVideo ? 90000 : 60000;
  }

  return Math.min(timeoutMs, isVideo ? 300000 : 180000);
}

function createClientSessionKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getClientSessionKey() {
  if (typeof window === "undefined") {
    return "";
  }

  let sessionKey = window.sessionStorage.getItem(CLIENT_SESSION_STORAGE_KEY);
  if (!sessionKey) {
    sessionKey = createClientSessionKey();
    window.sessionStorage.setItem(CLIENT_SESSION_STORAGE_KEY, sessionKey);
  }
  return sessionKey;
}

function withClientSessionHeaders(headers = {}) {
  const sessionKey = getClientSessionKey();
  return sessionKey ? { ...headers, "X-Client-Session": sessionKey } : headers;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 45000, kind = "Request") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(timeoutErrorMessage(kind, timeoutMs));
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    if (typeof payload === "string") {
      throw new Error(payload || "Request failed.");
    }

    if (payload?.detail) {
      throw new Error(payload.detail);
    }

    const firstKey = payload && Object.keys(payload)[0];
    if (firstKey && payload[firstKey]) {
      const value = Array.isArray(payload[firstKey]) ? payload[firstKey][0] : payload[firstKey];
      throw new Error(String(value));
    }

    throw new Error("Request failed.");
  }

  return payload;
}

export async function submitUploadDetection(file, clientMetadata = null) {
  const formData = new FormData();
  formData.append("file", file);
  if (clientMetadata) {
    formData.append("client_metadata", JSON.stringify(clientMetadata));
  }
  const timeoutMs = buildUploadTimeoutMs(file, clientMetadata);

  const response = await fetchWithTimeout(
    "/api/detect/upload/",
    {
      method: "POST",
      headers: withClientSessionHeaders(),
      body: formData,
    },
    timeoutMs,
    file.type.startsWith("video/") ? "Video detection" : "Image detection",
  );

  return parseResponse(response);
}

export async function submitUrlDetection(url) {
  const response = await fetchWithTimeout(
    "/api/detect/url/",
    {
      method: "POST",
      headers: withClientSessionHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({ url }),
    },
    30000,
    "URL detection",
  );

  return parseResponse(response);
}

export async function fetchDetectionHistory(page = 1) {
  const response = await fetch(`/api/results/?page=${page}`, {
    headers: withClientSessionHeaders(),
  });
  return parseResponse(response);
}

export async function resetClientSessionHistory() {
  if (typeof window === "undefined") {
    return;
  }

  const sessionKey = window.sessionStorage.getItem(CLIENT_SESSION_STORAGE_KEY);
  if (!sessionKey) {
    return;
  }

  window.sessionStorage.removeItem(CLIENT_SESSION_STORAGE_KEY);

  try {
    await fetch("/api/results/reset/", {
      method: "POST",
      headers: { "X-Client-Session": sessionKey },
      keepalive: true,
    });
  } catch {
    // A failed page-unload cleanup should not interrupt the user's navigation.
  }
}
