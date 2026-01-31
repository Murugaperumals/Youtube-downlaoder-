# YouTube Downloader

This is a simple web application that allows you to download YouTube videos, audio, and subtitles.

## Features

- Download YouTube videos in various qualities.
- Download audio only in MP3 format.
- Download subtitles in English.

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Murugaperumals/Youtube-downlaoder-.git
   ```

2. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```

4. **Open your browser and go to:**
   ```
   http://127.0.0.1:5000
   ```

## Usage

1. Paste the YouTube video URL into the input field.
2. Select the desired download options (video, audio, or subtitles).
3. Click the "Download" button.

## Project Structure

- `app.py`: The main Flask application file.
- `requirements.txt`: The list of Python dependencies.
- `templates/`: The directory containing the HTML templates.
- `static/`: The directory containing the static files (CSS and JavaScript).
- `temp_downloads/`: The directory where the downloaded files are temporarily stored.
- `ffmpeg-7.1.1-essentials_build/`: The directory containing the ffmpeg essentials build.
- `README.md`: This file.

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