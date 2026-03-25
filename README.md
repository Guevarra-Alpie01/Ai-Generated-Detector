# AI Media Detector

A production-aware Django + DRF + React application scaffold for detecting whether uploaded images, short MP4 videos, or public YouTube/Facebook links likely contain AI-generated media.

## Project structure

```text
aidetector/
├── detector/              # Detection APIs, scoring, throttling, inference orchestration
├── media_handler/         # Upload validation, image/video helpers, URL parsing/fetching
├── results/               # Detection history model and read APIs
├── frontend/              # React + Bootstrap frontend (Vite)
├── docs/                  # Deployment notes
├── templates/             # Django fallback template before frontend build exists
├── main/                  # Django project settings and root URLs
└── requirements.txt
```

## Detection strategy

- Image uploads use a lightweight ensemble of metadata checks, artifact heuristics, and an optional ONNX model hook for future CPU-safe upgrades.
- Videos sample a small number of frames, score each frame like an image, add a temporal consistency signal, and optionally analyze a short mono audio clip with lightweight heuristic features.
- URL analysis stays restricted to public YouTube/Facebook pages. The backend analyzes a public thumbnail or preview image only, so audio is intentionally skipped for those sources to keep synchronous requests realistic for PythonAnywhere free hosting.

## Local setup

1. Create and activate a virtualenv.
2. Install backend dependencies with `pip install -r requirements.txt`.
3. Run `python manage.py migrate`.
4. In `frontend/`, run `npm install` then `npm run build`.
5. Start Django with `python manage.py runserver`.

## Deployment

PythonAnywhere-specific notes live in [docs/pythonanywhere_free_plan.md](/c:/Users/arroy/Desktop/aidetector/docs/pythonanywhere_free_plan.md).
