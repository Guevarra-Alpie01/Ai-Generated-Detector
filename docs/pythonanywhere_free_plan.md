# PythonAnywhere Free Plan Deployment Notes

## Why this design fits the free plan

- Uses SQLite and filesystem storage only.
- Keeps inference synchronous and CPU-only.
- Limits uploaded media size and shortens video analysis to a few frames.
- Avoids background workers, Redis, Celery, and browser automation.

## Recommended deployment flow

1. Build the React frontend locally or on another machine with Node available.
2. Upload the repository with the generated `frontend/dist/` folder included.
3. Create a Python 3.13 virtualenv on PythonAnywhere and install `requirements.txt`.
4. Set environment variables in the WSGI file or Bash console.
5. Run:
   - `python manage.py migrate`
   - `python manage.py collectstatic --noinput`
6. Point the PythonAnywhere web app to:
   - code: project root
   - WSGI file: your Django `main/wsgi.py`
   - static URL: `/static/`
   - media URL: `/media/`

## Example environment variables

```bash
export DJANGO_SECRET_KEY='replace-me'
export DJANGO_DEBUG='False'
export DJANGO_ALLOWED_HOSTS='yourusername.pythonanywhere.com'
export DJANGO_CSRF_TRUSTED_ORIGINS='https://yourusername.pythonanywhere.com'
```

## Static and media handling

- `STATIC_ROOT` is `staticfiles/`
- `MEDIA_ROOT` is `media/`
- Vite should build with base `/static/`
- Django templates are configured to serve `frontend/dist/index.html`

## Operational notes

- Free accounts are not ideal for running a Node build pipeline on-host, so it is safer to build React locally and upload the generated assets.
- Facebook preview extraction depends on publicly accessible Open Graph metadata; private or login-gated links will fail validation.
- YouTube URL analysis intentionally uses thumbnails only to keep latency and CPU usage predictable.
