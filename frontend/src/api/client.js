function timeoutErrorMessage(kind, timeoutMs) {
  const seconds = Math.round(timeoutMs / 1000);
  return `${kind} took longer than ${seconds} seconds. Please try a smaller file or try again on a stronger connection.`;
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

export async function submitUploadDetection(file) {
  const formData = new FormData();
  formData.append("file", file);
  const timeoutMs = file.type.startsWith("video/") ? 90000 : 45000;

  const response = await fetchWithTimeout(
    "/api/detect/upload/",
    {
      method: "POST",
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
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url }),
    },
    30000,
    "URL detection",
  );

  return parseResponse(response);
}

export async function fetchDetectionHistory(page = 1) {
  const response = await fetch(`/api/results/?page=${page}`);
  return parseResponse(response);
}
