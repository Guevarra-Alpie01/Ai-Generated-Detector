# PythonAnywhere Bash Setup

This guide deploys the app as one Django site that serves both the built React frontend and the `/api/...` endpoints. That is the recommended PythonAnywhere free-plan setup because the frontend already calls relative API URLs, so the UI and API stay connected without adding CORS configuration.

## 1. Create the web app in the PythonAnywhere dashboard

1. Open the `Web` tab.
2. Click `Add a new web app`.
3. Choose `Manual configuration`.
4. Pick a Python version.

Use the same Python version for the web app and the virtualenv you create in Bash.

## 2. Open a Bash console and upload the project

If your code is in Git:

```bash
cd ~
git clone <your-repo-url> aidetector
cd ~/aidetector
```

If you uploaded a zip file instead:

```bash
cd ~
unzip aidetector.zip -d aidetector
cd ~/aidetector
```

## 3. Create a virtualenv that matches the web app

Check which Python versions are available:

```bash
ls /usr/bin/python3.*
```

Create the virtualenv with the same version you picked in the `Web` tab. Example:

```bash
mkvirtualenv --python=/usr/bin/python3.13 aidetector-env
workon aidetector-env
python --version
```

If `mkvirtualenv` is unavailable in your console, use:

```bash
python3.13 -m venv ~/.virtualenvs/aidetector-env
source ~/.virtualenvs/aidetector-env/bin/activate
python --version
```

## 4. Install backend dependencies

```bash
cd ~/aidetector
pip install --upgrade pip
pip install -r requirements.txt
```

If you previously hit a disk-quota error during `pip install`, clear the failed wheel cache and retry:

```bash
rm -rf ~/.cache/pip
pip install -r requirements.txt
```

## 5. Upload the built frontend

Build the React frontend on your own machine, then upload the generated `frontend/dist/` folder together with the project.

Local build command:

```bash
cd frontend
npm install
npm run build
```

Back on PythonAnywhere, confirm the built assets exist:

```bash
cd ~/aidetector
ls frontend/dist
```

If `frontend/dist/` is missing, the API can still run, but the full React UI will not be served.

## 6. Create the production env file

This project now auto-loads `.pythonanywhere.env` from:

- `manage.py`
- `main/wsgi.py`
- `main/asgi.py`

Create it from the example:

```bash
cd ~/aidetector
cp .env.example .pythonanywhere.env
nano .pythonanywhere.env
```

Minimum production values:

```bash
DJANGO_SECRET_KEY=replace-this-with-a-long-random-secret
DJANGO_DEBUG=False
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_ALLOWED_HOSTS=yourusername.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourusername.pythonanywhere.com
DJANGO_TIME_ZONE=Asia/Manila
TEMP_ANALYSIS_DIR=/home/yourusername/aidetector/tmp
ENABLE_AUDIO_ANALYSIS=True
ENABLE_URL_AUDIO_ANALYSIS=True
FFMPEG_BINARY=ffmpeg
ILLUMINARTY_ENABLED=False
ILLUMINARTY_API_KEY=
ILLUMINARTY_API_URL=
REALITY_DEFENDER_ENABLED=False
REALITY_DEFENDER_API_KEY=
REALITY_DEFENDER_API_URL=https://api.prd.realitydefender.xyz
```

Keep external providers disabled until you have valid credentials and have verified that PythonAnywhere free-plan networking can reach those API domains.

## 7. Prepare directories and run Django setup

```bash
cd ~/aidetector
workon aidetector-env
mkdir -p ~/aidetector/media ~/aidetector/staticfiles ~/aidetector/tmp
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Optional admin user:

```bash
python manage.py createsuperuser
```

Check whether `ffmpeg` is available for local audio and video analysis:

```bash
which ffmpeg || echo "ffmpeg not found"
```

If it is not available, set these in `.pythonanywhere.env`:

```bash
ENABLE_AUDIO_ANALYSIS=False
ENABLE_URL_AUDIO_ANALYSIS=False
```

## 8. Configure the web app in the `Web` tab

Set these values in PythonAnywhere:

- Source code: `/home/yourusername/aidetector`
- Working directory: `/home/yourusername/aidetector`
- Virtualenv: `/home/yourusername/.virtualenvs/aidetector-env`

Then open the generated WSGI file from the `Web` tab. On PythonAnywhere, this is the file under `/var/www/..._wsgi.py`, not your project file at `main/wsgi.py`.

Replace the Django section with:

```python
import os
import sys

project_home = "/home/yourusername/aidetector"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ.setdefault(
    "PYTHONANYWHERE_ENV_FILE",
    "/home/yourusername/aidetector/.pythonanywhere.env",
)

from main.wsgi import application
```

Save the file.

## 9. Add static and media mappings

In the `Static files` section of the `Web` tab, add:

- URL: `/static/` -> Directory: `/home/yourusername/aidetector/staticfiles`
- URL: `/media/` -> Directory: `/home/yourusername/aidetector/media`

Then click `Reload`.

## 10. Verify that the site and API are connected

Test these URLs in the browser:

- `https://yourusername.pythonanywhere.com/`
- `https://yourusername.pythonanywhere.com/api/results/`

Then test:

1. Upload a small JPG or PNG.
2. Upload a short MP4.
3. Try a YouTube URL.
4. Try a public Facebook URL with preview media.

Because the frontend uses relative `/api/...` paths, a same-origin deploy means the React UI should call the API without extra frontend changes.

## 11. External-provider note for free accounts

PythonAnywhere free accounts can only make outbound HTTP/HTTPS requests to allowlisted domains. That means:

- Illuminarty may still be skipped on the free plan if its API domain is not allowlisted.
- Reality Defender may still be skipped on the free plan if its API domain is not allowlisted.
- The local fallback pipeline is what keeps the app usable even when those external providers are unreachable.

If you need those providers live in production, either:

1. Request allowlisting for the provider API domain from PythonAnywhere, if the API is public and documented.
2. Upgrade to a paid PythonAnywhere account with unrestricted outbound internet access.

## 12. Updating the deployment later

Whenever you deploy a new version:

```bash
cd ~/aidetector
workon aidetector-env
git pull
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
```

If the frontend changed, upload the new `frontend/dist/` folder before reloading the web app.

Then go back to the `Web` tab and click `Reload`.

## Troubleshooting

- If the homepage loads a fallback page instead of the React app, `frontend/dist/` is missing.
- If uploads fail, verify `media/` and `tmp/` exist and are writable.
- If audio is always skipped, check `which ffmpeg` and your audio env flags.
- If Illuminarty or Reality Defender are always skipped, check their enable flags, keys, URLs, and PythonAnywhere outbound-network restrictions.
- If the app returns `400 Bad Request`, re-check `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- If the app returns `500`, inspect the error log from the `Web` tab after reloading.
