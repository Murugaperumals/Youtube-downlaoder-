from flask import Flask, request, render_template_string, send_file, after_this_request, jsonify, url_for
import os
import yt_dlp
import uuid
import shutil
import threading
import time

app = Flask(__name__)

TEMP_DIR = 'temp_downloads'
os.makedirs(TEMP_DIR, exist_ok=True)

# Resolve ffmpeg location in a cross-platform way. Prefer system ffmpeg if available,
# otherwise fall back to a local ./ffmpeg.exe (keeps compatibility with the repo's
# Windows binary). If neither exists, leave as None so yt-dlp can try defaults.
FFMPEG_LOCATION = shutil.which('ffmpeg') or (os.path.abspath('./ffmpeg.exe') if os.path.exists(os.path.abspath('./ffmpeg.exe')) else None)

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
                # set ffmpeg_location only when we resolved a usable path
                **({'ffmpeg_location': FFMPEG_LOCATION} if FFMPEG_LOCATION else {}),
                
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
                **({'ffmpeg_location': FFMPEG_LOCATION} if FFMPEG_LOCATION else {}),
                
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


# Simple in-memory job tracking. For production use a persistent queue (Redis/Celery/RQ).
JOBS = {}
JOBS_LOCK = threading.Lock()


def start_download_job(url, audio_only=False, subs_only=False):
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {'status': 'queued', 'file': None, 'error': None, 'title': None, 'progress': None}

    def _worker():
        with JOBS_LOCK:
            JOBS[job_id]['status'] = 'running'

        # define a progress hook for yt-dlp
        def hook(d):
            try:
                status = d.get('status')
                with JOBS_LOCK:
                    if status == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes') or 0
                        percent = None
                        if total:
                            try:
                                percent = int(downloaded * 100 / total)
                            except Exception:
                                percent = None
                        JOBS[job_id]['progress'] = {'status': 'downloading', 'downloaded': downloaded, 'total': total, 'percent': percent, 'eta': d.get('eta')}
                    elif status == 'finished':
                        JOBS[job_id]['progress'] = {'status': 'finished'}
                    else:
                        JOBS[job_id]['progress'] = {'status': status}
            except Exception:
                pass

        file_path, title_or_error = download_video_to_file(url, audio_only=audio_only, subs_only=subs_only, progress_hook=hook)
        with JOBS_LOCK:
            if file_path:
                JOBS[job_id].update({'status': 'finished', 'file': file_path, 'title': title_or_error})
            else:
                JOBS[job_id].update({'status': 'error', 'error': title_or_error})

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id

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


status_page_template = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Download status</title>
    <style>
        .progress-wrap { width: 100%; max-width: 600px; }
        .progress { width: 100%; height: 20px; background: #eee; border-radius: 4px; overflow: hidden; }
        .progress > .bar { height: 100%; width: 0%; background: #4caf50; transition: width 0.4s ease; }
        .meta { margin-top: 8px; font-size: 0.9rem; }
    </style>
</head>
<body>
<h2>Download started</h2>
<p>Job ID: {{ job_id }}</p>
<div class="progress-wrap">
    <div class="progress"><div id="bar" class="bar"></div></div>
    <div class="meta"><span id="percent">Queued</span> — <span id="eta"></span></div>
</div>
<div id="actions" style="margin-top:12px"></div>

<script>
    function fmtBytes(n){ if(!n) return ''; if(n<1024) return n+' B'; if(n<1024*1024) return (n/1024).toFixed(1)+' KB'; return (n/1024/1024).toFixed(2)+' MB'; }

    function updateUI(data){
        var p = data.progress || {};
        var percent = p.percent;
        if(data.status === 'finished') percent = 100;
        if(percent || percent === 0){
            document.getElementById('bar').style.width = percent + '%';
            document.getElementById('percent').innerText = (percent===100? 'Completed (100%)' : (percent + '%'));
        } else {
            document.getElementById('percent').innerText = data.status;
        }
        if(p.eta) document.getElementById('eta').innerText = 'ETA: ' + p.eta; else document.getElementById('eta').innerText = '';
        if(data.status === 'finished'){
            document.getElementById('actions').innerHTML = '<a href="'+data.download_url+'">Download file</a>';
        } else if(data.status === 'error'){
            document.getElementById('actions').innerText = 'Error: ' + (data.error || 'unknown');
        }
    }

    function check(){
        fetch('{{ status_url }}')
            .then(r=>r.json())
            .then(data=>{
                updateUI(data);
                if(data.status !== 'finished' && data.status !== 'error') setTimeout(check, 1500);
            })
            .catch(e=>{ document.getElementById('actions').innerText = 'Error checking status'; });
    }
    check();
</script>
</body>
</html>
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


@app.route('/status/<job_id>', methods=['GET'])
def job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({'status': 'not_found'}), 404
        if job['status'] == 'finished':
            download_url = url_for('job_download', job_id=job_id, _external=True)
            prog = job.get('progress') or {}
            # set 100% when finished if percent missing
            if not prog.get('percent'):
                prog['percent'] = 100
            prog['status'] = 'finished'
            return jsonify({'status': 'finished', 'download_url': download_url, 'title': job.get('title'), 'progress': prog})
        if job['status'] == 'error':
            return jsonify({'status': 'error', 'error': job.get('error'), 'progress': job.get('progress')}), 200
        return jsonify({'status': job['status'], 'progress': job.get('progress')}), 200


@app.route('/download/<job_id>', methods=['GET'])
def job_download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return "Not found", 404
        if job['status'] != 'finished' or not job.get('file'):
            return "Not ready", 400
        file_path = job['file']
        
        # Clean up any temp cookie files that might be left
        for f in os.listdir(TEMP_DIR):
            if f.startswith('cookies_') and f.endswith('.txt'):
                try:
                    os.remove(os.path.join(TEMP_DIR, f))
                except:
                    pass

    @after_this_request
    def cleanup(response):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Cleanup error: {e}")
        # remove job record
        with JOBS_LOCK:
            try:
                del JOBS[job_id]
            except Exception:
                pass
        return response

    # serve file
    mimetype = 'audio/mp3' if file_path.endswith('.mp3') else ('text/vtt' if file_path.endswith('.vtt') else 'application/octet-stream')
    return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path), mimetype=mimetype)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
