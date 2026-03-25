from PIL import ImageChops, ImageFilter, ImageStat


def analyse_image_statistics(image):
    grayscale = image.convert("L")
    hsv = image.convert("HSV")

    grayscale_stats = ImageStat.Stat(grayscale)
    hsv_stats = ImageStat.Stat(hsv)

    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    edge_mean = ImageStat.Stat(edges).mean[0] / 255

    filtered = grayscale.filter(ImageFilter.MedianFilter(size=3))
    diff = ImageChops.difference(grayscale, filtered)
    local_noise = ImageStat.Stat(diff).mean[0] / 255

    return {
        "width": image.width,
        "height": image.height,
        "brightness": grayscale_stats.mean[0] / 255,
        "contrast": grayscale_stats.stddev[0] / 255,
        "saturation": hsv_stats.mean[1] / 255,
        "entropy": grayscale.entropy(),
        "edge_density": edge_mean,
        "local_noise": local_noise,
    }
