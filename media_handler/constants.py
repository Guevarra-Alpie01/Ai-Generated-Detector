class SourceTypes:
    IMAGE = "image"
    VIDEO = "video"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"

    CHOICES = (
        (IMAGE, "Image"),
        (VIDEO, "Video"),
        (YOUTUBE, "YouTube"),
        (FACEBOOK, "Facebook"),
    )


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4"}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
VIDEO_MIME_TYPES = {"video/mp4", "application/mp4"}

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch"}
FACEBOOK_MEDIA_HOST_SUFFIXES = (".fbcdn.net",)
