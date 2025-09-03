from flask import Flask, request, render_template_string, send_file, after_this_request
import os
import yt_dlp
import uuid
import shutil

app = Flask(__name__)

TEMP_DIR = 'temp_downloads'
os.makedirs(TEMP_DIR, exist_ok=True)

# Download function: returns file path and filename
def download_video_to_file(url, audio_only=False, subs_only=False):
    try:
        temp_filename = str(uuid.uuid4())
        output_template = os.path.join(TEMP_DIR, f"{temp_filename}.%(ext)s")

        if subs_only:
            ydl_opts = {
                'writesubtitles': True,
                'subtitleslangs': ['en'],
                'skip_download': True,
                'writeautomaticsub': True,
                'outtmpl': output_template,
                'quiet': True,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'extract_flat': False
            }
        elif audio_only:
            ydl_format = 'bestaudio[ext=m4a]/bestaudio/best'
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            ydl_opts = {
                'format': ydl_format,
                'outtmpl': output_template,
                'ffmpeg_location': os.path.abspath('./ffmpeg.exe'),
                'quiet': True,
                'postprocessors': postprocessors,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'extract_flat': False,
                'writesubtitles': True,
                'subtitleslangs': ['en'],
                'skip_download': False,
                'writeautomaticsub': True
            }
        else:
            ydl_format = 'bestvideo+bestaudio/best'  # Most compatible for all videos
            postprocessors = []
            ydl_opts = {
                'format': ydl_format,
                'outtmpl': output_template,
                'ffmpeg_location': os.path.abspath('./ffmpeg.exe'),
                'quiet': True,
                'postprocessors': postprocessors,
                'nocheckcertificate': True,  # Ignore SSL certificate errors
                'ignoreerrors': True,        # Ignore errors and continue
                'extract_flat': False        # Ensure full extraction, not flat
                # 'noplaylist': True  # REMOVE this line to allow playlist downloads
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if subs_only:
                # Find the subtitle file
                subs = info.get('requested_subtitles', {})
                if subs and 'en' in subs:
                    sub_file = os.path.splitext(output_template)[0] + '.en.vtt'
                    return sub_file, info.get('title', 'subtitles')
                return None, "No English subtitles found for this video."
            # If a playlist, download all videos
            if 'entries' in info:
                downloaded_files = []
                for entry in info['entries']:
                    # Skip DRM protected or unavailable videos
                    if entry is None or entry.get('is_live') or entry.get('drm_family'):
                        continue
                    file_path = ydl.prepare_filename(entry)
                    if audio_only:
                        file_path = os.path.splitext(file_path)[0] + ".mp3"
                    downloaded_files.append((file_path, entry.get('title', 'downloaded_file')))
                if not downloaded_files:
                    return None, "No downloadable videos found in playlist."
                # Return first file for browser download, but you can customize to zip all
                return downloaded_files[0][0], downloaded_files[0][1]
            else:
                downloaded_file = ydl.prepare_filename(info)
                if audio_only:
                    downloaded_file = os.path.splitext(downloaded_file)[0] + ".mp3"
                return downloaded_file, info.get('title', 'downloaded_file')
    except Exception as e:
        return None, f"Error: {e}"

# HTML form with progress bar and audio-only checkbox (NO resolution)
form_html = '''
<!DOCTYPE html>
<h2>YouTube Downloader</h2>
<form method="post" onsubmit="showProgress()">
    <label>YouTube URL:</label><br>
    <input name="url" size="60" required><br><br>

    <input type="checkbox" name="audio_only" id="audio_only">
    <label for="audio_only">Audio Only (MP3)</label><br><br>

    <input type="checkbox" name="subs_only" id="subs_only">
    <label for="subs_only">Download Subtitles Only (EN)</label><br><br>

    <button type="submit">Download</button>
    <div id="progress" style="display:none;">⏳ Downloading, please wait...</div>
</form>

<script>
    function showProgress() {
        document.getElementById('progress').style.display = 'block';
    }
</script>

{% if error %}
<p style="color:red;"><strong>{{ error }}</strong></p>
{% endif %}
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form['url']
        audio_only = 'audio_only' in request.form
        subs_only = 'subs_only' in request.form

        file_path, title_or_error = download_video_to_file(url, audio_only, subs_only)

        if file_path:
            @after_this_request
            def cleanup(response):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Cleanup error: {e}")
                return response

            # Set mimetype for subtitle download
            if subs_only:
                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=os.path.basename(file_path),
                    mimetype='text/vtt'
                )
            return send_file(
                file_path,
                as_attachment=True,
                download_name=os.path.basename(file_path),
                mimetype='audio/mp3' if audio_only else 'video/mp4'
            )
        else:
            return render_template_string(form_html, error=title_or_error)

    return render_template_string(form_html)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
