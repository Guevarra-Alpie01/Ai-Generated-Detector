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

  const response = await fetch("/api/detect/upload/", {
    method: "POST",
    body: formData,
  });

  return parseResponse(response);
}

export async function submitUrlDetection(url) {
  const response = await fetch("/api/detect/url/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url }),
  });

  return parseResponse(response);
}

export async function fetchDetectionHistory(page = 1) {
  const response = await fetch(`/api/results/?page=${page}`);
  return parseResponse(response);
}
