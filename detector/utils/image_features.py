from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


def _load_numpy():
    try:
        import numpy as imported_numpy
    except Exception:  # pragma: no cover - fallback exercised in deployments where numpy is missing or broken
        return None
    return imported_numpy


try:
    np = _load_numpy()
except Exception:  # pragma: no cover - extra safety for unusual interpreter import failures
    np = None


def prepare_working_image(image: Image.Image, max_dimension: int) -> Image.Image:
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    prepared.thumbnail((max_dimension, max_dimension))
    return prepared


def _histogram_fill_ratio(histogram: list[int]) -> float:
    return sum(1 for value in histogram if value) / max(1, len(histogram))


def _frequency_metrics_fft(grayscale: Image.Image) -> dict[str, float]:
    spectrum_input = grayscale.resize((128, 128))
    values = np.asarray(spectrum_input, dtype=np.float32)
    fft = np.fft.fftshift(np.fft.fft2(values))
    magnitude = np.abs(fft)
    total_energy = float(magnitude.sum()) or 1.0

    rows, cols = values.shape
    center_y, center_x = rows // 2, cols // 2
    yy, xx = np.ogrid[:rows, :cols]
    radius = np.sqrt((yy - center_y) ** 2 + (xx - center_x) ** 2)
    radius_max = float(radius.max()) or 1.0

    low_mask = radius <= radius_max * 0.12
    high_mask = radius >= radius_max * 0.45
    mid_mask = (~low_mask) & (~high_mask)

    row_energy = magnitude.sum(axis=1)
    column_energy = magnitude.sum(axis=0)
    row_mean = float(row_energy.mean()) or 1.0
    column_mean = float(column_energy.mean()) or 1.0
    spike_threshold = float(np.percentile(magnitude, 99.8))

    return {
        "low_frequency_ratio": float(magnitude[low_mask].sum() / total_energy),
        "mid_frequency_ratio": float(magnitude[mid_mask].sum() / total_energy),
        "high_frequency_ratio": float(magnitude[high_mask].sum() / total_energy),
        "frequency_direction_bias": abs(row_mean - column_mean) / max(row_mean, column_mean, 1e-6),
        "spectral_spike_ratio": float((magnitude >= spike_threshold).sum() / magnitude.size),
    }


def _frequency_metrics_fallback(grayscale: Image.Image) -> dict[str, float]:
    spectrum_input = grayscale.resize((128, 128))
    low_band = spectrum_input.filter(ImageFilter.GaussianBlur(radius=3.2))
    mid_base = spectrum_input.filter(ImageFilter.GaussianBlur(radius=1.6))
    mid_band = ImageChops.difference(mid_base, low_band)
    high_band = ImageChops.difference(spectrum_input, mid_base)

    low_energy = ImageStat.Stat(low_band).mean[0]
    mid_energy = ImageStat.Stat(mid_band).mean[0]
    high_energy = ImageStat.Stat(high_band).mean[0]
    total_energy = max(low_energy + mid_energy + high_energy, 1e-6)

    horizontal = spectrum_input.filter(
        ImageFilter.Kernel((3, 3), [-1, -2, -1, 0, 0, 0, 1, 2, 1], scale=1)
    )
    vertical = spectrum_input.filter(
        ImageFilter.Kernel((3, 3), [-1, 0, 1, -2, 0, 2, -1, 0, 1], scale=1)
    )
    horizontal_energy = ImageStat.Stat(horizontal).mean[0]
    vertical_energy = ImageStat.Stat(vertical).mean[0]
    high_histogram = high_band.histogram()
    total_pixels = max(1, spectrum_input.width * spectrum_input.height)

    return {
        "low_frequency_ratio": float(low_energy / total_energy),
        "mid_frequency_ratio": float(mid_energy / total_energy),
        "high_frequency_ratio": float(high_energy / total_energy),
        "frequency_direction_bias": abs(horizontal_energy - vertical_energy)
        / max(horizontal_energy, vertical_energy, 1e-6),
        "spectral_spike_ratio": float(sum(high_histogram[224:]) / total_pixels),
    }


def _frequency_metrics(grayscale: Image.Image) -> dict[str, float]:
    if np is None:
        return _frequency_metrics_fallback(grayscale)
    try:
        return _frequency_metrics_fft(grayscale)
    except Exception:  # pragma: no cover - fallback exercised when numpy fft is unavailable or misconfigured
        return _frequency_metrics_fallback(grayscale)


def analyse_image_features(image: Image.Image) -> dict[str, float]:
    grayscale = image.convert("L")
    saturation_channel = image.convert("HSV").getchannel("S")

    grayscale_stats = ImageStat.Stat(grayscale)
    saturation_stats = ImageStat.Stat(saturation_channel)

    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    edge_stats = ImageStat.Stat(edges)

    median_filtered = grayscale.filter(ImageFilter.MedianFilter(size=3))
    local_noise_image = ImageChops.difference(grayscale, median_filtered)
    local_noise_stats = ImageStat.Stat(local_noise_image)

    softened = grayscale.filter(ImageFilter.GaussianBlur(radius=1.4))
    detail_residual_image = ImageChops.difference(grayscale, softened)
    detail_residual_stats = ImageStat.Stat(detail_residual_image)

    grayscale_histogram = grayscale.histogram()
    saturation_histogram = saturation_channel.histogram()
    total_pixels = max(1, image.width * image.height)
    frequency_metrics = _frequency_metrics(grayscale)

    return {
        "width": image.width,
        "height": image.height,
        "brightness": grayscale_stats.mean[0] / 255,
        "contrast": grayscale_stats.stddev[0] / 255,
        "saturation": saturation_stats.mean[0] / 255,
        "saturation_spread": saturation_stats.stddev[0] / 255,
        "entropy": grayscale.entropy(),
        "edge_density": edge_stats.mean[0] / 255,
        "edge_variation": edge_stats.stddev[0] / 255,
        "local_noise": local_noise_stats.mean[0] / 255,
        "noise_variation": local_noise_stats.stddev[0] / 255,
        "detail_residual": detail_residual_stats.mean[0] / 255,
        "detail_variation": detail_residual_stats.stddev[0] / 255,
        "shadow_clip": sum(grayscale_histogram[:8]) / total_pixels,
        "highlight_clip": sum(grayscale_histogram[-8:]) / total_pixels,
        "histogram_fill": _histogram_fill_ratio(grayscale_histogram),
        "saturation_histogram_fill": _histogram_fill_ratio(saturation_histogram),
        **frequency_metrics,
    }
