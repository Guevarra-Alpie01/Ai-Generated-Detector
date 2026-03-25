# PythonAnywhere Free Plan Deployment Notes

For a copy-paste-friendly Bash walkthrough, use [pythonanywhere_bash_setup.md](/c:/Users/arroy/Desktop/aidetector/docs/pythonanywhere_bash_setup.md).

## Why this design fits the free plan

- Uses SQLite and filesystem storage only.
- Keeps inference synchronous and CPU-only.
- Always runs a lightweight local fallback first, so uploads still complete when external APIs are disabled, slow, or out of quota.
- Limits uploaded media size and shortens video analysis to a few frames.
- Avoids the large OpenCV wheel in the default install, using `ffmpeg/ffprobe` for bounded video frame extraction instead.
- Limits audio analysis to a short mono clip and skips it entirely if ffmpeg is unavailable or the source has no usable audio stream.
- Uses thumbnail or preview extraction for public YouTube and Facebook URLs instead of downloading whole remote videos.
- Avoids background workers, Redis, Celery, and browser automation.
- Stores only compact provider payload previews so SQLite does not fill up with large raw API blobs.

## Recommended deployment flow

1. Build the React frontend locally or on another machine with Node available.
2. Upload the repository with the generated `frontend/dist/` folder included.
3. Create a Python 3.13 virtualenv on PythonAnywhere and install `requirements.txt`.
4. Copy `.env.example` to `.pythonanywhere.env` and set production values there.
5. Run:
   - `python manage.py migrate`
   - `python manage.py collectstatic --noinput`
   - `python manage.py check --deploy`
6. Point the PythonAnywhere web app to:
   - code: project root
   - WSGI file: PythonAnywhere's generated `/var/www/..._wsgi.py`, configured to import `main.wsgi`
   - static URL: `/static/`
   - media URL: `/media/`

## Example environment variables

```bash
export DJANGO_SECRET_KEY='replace-me'
export DJANGO_DEBUG='False'
export DJANGO_ALLOWED_HOSTS='yourusername.pythonanywhere.com'
export DJANGO_CSRF_TRUSTED_ORIGINS='https://yourusername.pythonanywhere.com'
export TEMP_ANALYSIS_DIR='/home/yourusername/aidetector/tmp'
export ENABLE_AUDIO_ANALYSIS='True'
export ENABLE_URL_AUDIO_ANALYSIS='True'
export MAX_AUDIO_ANALYSIS_SECONDS='10'
export AUDIO_ANALYSIS_SAMPLE_RATE='16000'
export AUDIO_ANALYSIS_TIMEOUT_SECONDS='8'
export FFMPEG_BINARY='ffmpeg'
export URL_FETCH_MAX_VIDEO_BYTES='12582912'
export DETECTION_LABEL_LOW_THRESHOLD='0.35'
export DETECTION_LABEL_HIGH_THRESHOLD='0.68'
export LOCAL_ONLY_LABEL_LOW_THRESHOLD='0.46'
export LOCAL_ONLY_LABEL_HIGH_THRESHOLD='0.78'
export LOCAL_ONLY_COMPONENT_SPREAD_THRESHOLD='0.24'
export DETECTION_PROVIDER_WEIGHTS='{"local":0.45,"illuminarty":0.30,"reality_defender":0.25}'
export ILLUMINARTY_ENABLED='False'
export ILLUMINARTY_API_KEY=''
export ILLUMINARTY_API_URL=''
export REALITY_DEFENDER_ENABLED='False'
export REALITY_DEFENDER_API_KEY=''
export REALITY_DEFENDER_API_URL='https://api.prd.realitydefender.xyz'
export REALITY_DEFENDER_SOFT_LIMIT_PER_DAY='20'
```

## Static and media handling

- `STATIC_ROOT` is `staticfiles/`
- `MEDIA_ROOT` is `media/`
- Vite should build with base `/static/`
- Django templates are configured to serve `frontend/dist/index.html`

## Operational notes

- Free accounts are not ideal for running a Node build pipeline on-host, so it is safer to build React locally and upload the generated assets.
- This project now auto-loads a project-level `.pythonanywhere.env` file from `manage.py`, `main/wsgi.py`, and `main/asgi.py`, so one env file can drive both Bash commands and the live web app.
- The deployed frontend calls relative `/api/...` URLs, so the recommended PythonAnywhere setup is one Django site serving both UI and API on the same domain.
- Keep `ILLUMINARTY_ENABLED` and `REALITY_DEFENDER_ENABLED` off until the matching credentials and endpoint URLs are present. Disabled providers are skipped cleanly and the local fallback still runs.
- Free PythonAnywhere accounts only have outbound access to allowlisted domains. If the Illuminarty or Reality Defender API domains are not on PythonAnywhere's allowlist, those providers will fail on the free plan and the local fallback will remain the active path unless you request allowlisting or upgrade to a paid account.
- Reality Defender is integrated behind a soft daily quota guard in SQLite. If the local guard reaches its limit or the API returns quota/rate-limit errors, the request falls back to local analysis instead of failing outright.
- Facebook preview extraction depends on publicly accessible Open Graph metadata; private or login-gated links will fail validation.
- Facebook public links can use a small preview video when one is exposed publicly, which allows bounded local audio analysis without downloading the full original post.
- YouTube URL analysis intentionally uses thumbnails only to keep latency and CPU usage predictable, so audio remains unavailable for YouTube URL mode on the free plan.
- Audio extraction prefers `ffmpeg` when it is available. If `ffmpeg` is missing or the source video has no usable audio stream, the request falls back to visual-only scoring instead of failing.
- Large remote videos are not fetched in v1. Video uploads are analyzed locally, and external video-provider hooks remain disabled by default for free-plan deployments.
