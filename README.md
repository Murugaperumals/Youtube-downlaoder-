# Youtube-downloader
Youtube downloader + Subtitle also

## Deploying publicly

This repo contains a small Flask web UI that uses `yt-dlp` to download videos, audio, and subtitles.

Two quick deployment options are provided below:

1) Platform-as-a-Service (Heroku / Render / similar)

- Use the provided `Procfile` and `requirements-prod.txt`.
- Make sure the platform installs system `ffmpeg` (many do; on Render you can use a Docker deploy or install via apt in a build step).
- The `Procfile` starts the app with Gunicorn.

2) Docker (recommended for portability)

Build and run the container locally:

```bash
# build image
docker build -t yt-downloader:latest .

# run (binds container port 5000 to host 5000)
docker run -p 5000:5000 yt-downloader:latest
```

Then open http://localhost:5000 in your browser.

Notes:
- The app will attempt to detect system `ffmpeg`. If you have a local `ffmpeg.exe` in the repo root (Windows), the app will fall back to it.
- For PaaS deployments, ensure `ffmpeg` is available in the runtime. If your platform doesn't provide it, prefer Docker.

If you want, I can prepare a one-click Deploy file for a specific provider (e.g., Render or Railway) — tell me which provider and I'll add it.
