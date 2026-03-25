from PIL import ImageChops, ImageFilter, ImageStat


def _histogram_fill_ratio(histogram: list[int]) -> float:
    return sum(1 for value in histogram if value) / max(1, len(histogram))


def analyse_image_statistics(image):
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
    }
