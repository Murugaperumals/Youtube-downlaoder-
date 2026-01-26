# YouTube Downloader

This is a simple web application that allows you to download YouTube videos, audio, and subtitles.

## Features

- Download YouTube videos in various qualities.
- Download audio only in MP3 format.
- Download subtitles in English.

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/your-repository.git
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

1. Paste the YouTube video URL into the input field and click "Get Video".
2. Select the desired download options (audio only, subtitles only, or video quality).
3. The download will start automatically.

## Project Structure

- `app.py`: The main Flask application file.
- `requirements.txt`: The list of Python dependencies.
- `templates/`: The directory containing the HTML templates.
- `static/`: The directory containing the static files (CSS and JavaScript).
- `temp_downloads/`: The directory where the downloaded files are temporarily stored.
- `ffmpeg-7.1.1-essentials_build/`: The directory containing the ffmpeg essentials build.
- `README.md`: This file.