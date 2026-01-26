<<<<<<< HEAD
from flask import Flask, request, render_template, send_file, after_this_request
=======
from flask import Flask, request, render_template_string, send_file, after_this_request, jsonify, url_for
>>>>>>> 793ed659df8cb1b901b8470ef1f4158f973b4d84
import os
import glob
import mimetypes
import requests
import time
import http.cookiejar as cookiejar
# Optional transcript API for better automatic caption handling/translation
try:
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    HAS_YT_TRANSCRIPT_API = True
except Exception:
    YouTubeTranscriptApi = None
    TranscriptsDisabled = None
    NoTranscriptFound = None
    HAS_YT_TRANSCRIPT_API = False

# Optional translator (deep-translator)
try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except Exception:
    GoogleTranslator = None
    HAS_TRANSLATOR = False

import yt_dlp
import uuid
import shutil
import threading
import time

app = Flask(__name__)

TEMP_DIR = os.path.abspath('temp_downloads')
os.makedirs(TEMP_DIR, exist_ok=True)

<<<<<<< HEAD
# Try to locate bundled ffmpeg if available
FFMPEG_PATH = os.path.abspath(os.path.join('ffmpeg-7.1.1-essentials_build', 'bin', 'ffmpeg.exe'))


def _find_subtitle_url(subs_sources, lang='en'):
    """Robustly find a subtitle URL and extension for the given language from
    various shapes that yt-dlp may return (requested_subtitles, subtitles,
    automatic_captions). Returns (url, ext) or (None, None).
    """
    if not subs_sources or not isinstance(subs_sources, dict):
        return None, None

    entry = subs_sources.get(lang) or subs_sources.get(lang.lower())
    if entry is None:
        return None, None

    # Try several possible shapes
    def try_entry(e):
        # Direct URL string
        if isinstance(e, str):
            return e, 'vtt'
        # If it's a dict that may contain 'url' or map formats to lists
        if isinstance(e, dict):
            if 'url' in e:
                return e.get('url'), e.get('ext') or 'vtt'
            # Format -> list
            for fmt, val in e.items():
                if isinstance(val, list) and val:
                    first = val[0]
                    if isinstance(first, dict) and first.get('url'):
                        return first.get('url'), fmt or first.get('ext') or 'vtt'
                elif isinstance(val, dict) and val.get('url'):
                    return val.get('url'), fmt or val.get('ext') or 'vtt'
        # If it's a list of entries
        if isinstance(e, list) and e:
            first = e[0]
            if isinstance(first, dict) and first.get('url'):
                return first.get('url'), first.get('ext') or 'vtt'
            if isinstance(first, str):
                return first, 'vtt'
        return None, None

    return try_entry(entry)


def _extract_youtube_id(url):
    """Extract YouTube video ID from a few common URL formats."""
    import re
    match = re.search(r'(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})', url)
    return match.group(1) if match else None


def _write_transcript_vtt(transcript, path):
    """Write a list of transcript segments to a VTT file.
    transcript: list of {'text', 'start', 'duration'}
    """
    def fmt(t):
        hours = int(t // 3600)
        mins = int((t % 3600) // 60)
        secs = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{hours:02d}:{mins:02d}:{secs:02d}.{ms:03d}"

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('WEBVTT\n\n')
        for seg in transcript:
            start = seg.get('start', 0)
            dur = seg.get('duration', 0.0)
            end = start + dur
            fh.write(f"{fmt(start)} --> {fmt(end)}\n")
            fh.write(seg.get('text', '').replace('\n', ' ') + '\n\n')


def _get_with_retries(url, session=None, proxies=None, retries=4, backoff_factor=1, timeout=30):
    """GET a URL with simple exponential backoff on 429 responses. Returns requests.Response or None if rate-limited."""
    for attempt in range(retries):
        try:
            if session:
                resp = session.get(url, timeout=timeout, proxies=proxies)
            else:
                resp = requests.get(url, timeout=timeout, proxies=proxies)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as he:
            status = None
            try:
                status = he.response.status_code
            except Exception:
                status = None
            if status == 429:
                sleep_time = backoff_factor * (2 ** attempt)
                app.logger.warning("HTTP 429 fetching %s; sleeping %s sec (attempt %s)", url, sleep_time, attempt+1)
                time.sleep(sleep_time)
                continue
            app.logger.exception("HTTP error fetching %s: %s", url, he)
            raise
        except Exception as e:
            app.logger.exception("Error fetching %s: %s", url, e)
            raise
    # If we hit 429 every time, return None to signal rate limiting
    return None

=======
# Resolve ffmpeg location in a cross-platform way. Prefer system ffmpeg if available,
# otherwise fall back to a local ./ffmpeg.exe (keeps compatibility with the repo's
# Windows binary). If neither exists, leave as None so yt-dlp can try defaults.
FFMPEG_LOCATION = shutil.which('ffmpeg') or (os.path.abspath('./ffmpeg.exe') if os.path.exists(os.path.abspath('./ffmpeg.exe')) else None)
>>>>>>> 793ed659df8cb1b901b8470ef1f4158f973b4d84

# Download function: returns file path and filename
def download_video_to_file(url, audio_only=False, subs_only=False, cookies_file=None, proxy=None, quality=None):
    try:
        # Prepare requests session with optional cookies and proxy
        session = requests.Session()
        proxies = None
        proxy_valid = False
        if proxy:
            proxies = {'http': proxy, 'https': proxy}
            # Test proxy quickly to ensure it's usable before configuring yt-dlp
            try:
                session.proxies.update(proxies)
                # A lightweight test against youtube homepage
                test_resp = session.get('https://www.youtube.com', timeout=5)
                if test_resp.status_code < 400:
                    proxy_valid = True
                else:
                    app.logger.warning('Proxy test returned status %s; ignoring proxy', test_resp.status_code)
                    # clear proxies
                    session.proxies.clear()
                    proxies = None
            except Exception as e:
                app.logger.warning('Proxy test failed; will retry without proxy: %s', e)
                session.proxies.clear()
                proxies = None

        # Load cookies if a cookies file (Netscape format) was provided
        if cookies_file and os.path.isfile(cookies_file):
            try:
                jar = cookiejar.MozillaCookieJar()
                jar.load(cookies_file, ignore_discard=True, ignore_expires=True)
                session.cookies = jar
            except Exception:
                app.logger.exception('Failed to load cookies file: %s', cookies_file)

        temp_filename = str(uuid.uuid4())
        output_template = os.path.join(TEMP_DIR, f"{temp_filename}.%(ext)s")
        app.logger.debug(f"Output template: {output_template}")

        # Map quality to height filter
        quality_map = {
            '144p': '144',
            '240p': '240',
            '360p': '360',
            '480p': '480',
            '720p': '720',
            '1080p': '1080',
            '1440p': '1440',
            '2160p': '2160'
        }
        
        height_filter = None
        if quality and quality in quality_map:
            height_filter = quality_map[quality]

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
                'extract_flat': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            # Not strictly required for subtitles, but use bundled ffmpeg if present
            if os.path.exists(FFMPEG_PATH):
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            if proxy:
                ydl_opts['proxy'] = proxy
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
<<<<<<< HEAD
=======
                # set ffmpeg_location only when we resolved a usable path
                **({'ffmpeg_location': FFMPEG_LOCATION} if FFMPEG_LOCATION else {}),
                
>>>>>>> 793ed659df8cb1b901b8470ef1f4158f973b4d84
                'quiet': True,
                'postprocessors': postprocessors,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'extract_flat': False,
                'writesubtitles': True,
                'subtitleslangs': ['en'],
                'skip_download': False,
                'writeautomaticsub': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            if os.path.exists(FFMPEG_PATH):
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            if proxy:
                ydl_opts['proxy'] = proxy
        else:
            # Set format based on quality if specified - use simpler format for faster downloads
            if height_filter and not audio_only:
                ydl_format = f'bestvideo[height<=?{height_filter}]+bestaudio[ext=m4a]/best'
            else:
                ydl_format = 'bestvideo+bestaudio/best'
            postprocessors = []
            ydl_opts = {
                'format': ydl_format,
                'outtmpl': output_template,
<<<<<<< HEAD
=======
                **({'ffmpeg_location': FFMPEG_LOCATION} if FFMPEG_LOCATION else {}),
                
>>>>>>> 793ed659df8cb1b901b8470ef1f4158f973b4d84
                'quiet': True,
                'postprocessors': postprocessors,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'extract_flat': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            if os.path.exists(FFMPEG_PATH):
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            if proxy:
                ydl_opts['proxy'] = proxy

        # Try to extract info, retrying without proxy or with cookies if proxy caused failures
        extract_exception = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            extract_exception = e
            estr = str(e).lower()
            app.logger.exception('Initial extract_info error: %s', e)
            # If proxy was set and error indicates a proxy/connect issue, retry without proxy
            if proxy and not proxy_valid and ('proxy' in estr or 'tunnel' in estr or 'proxyerror' in estr or 'unable to connect to proxy' in estr):
                app.logger.warning('Proxy failed during extraction; retrying without proxy...')
                # Remove proxy from opts and retry
                ydl_opts.pop('proxy', None)
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        extract_exception = None
                except Exception as e2:
                    extract_exception = e2
                    app.logger.exception('Retry (no proxy) failed: %s', e2)
            else:
                # If proxy was set but validation succeeded earlier, still try fallback without proxy
                if proxy and proxy_valid:
                    app.logger.warning('Proxy was validated earlier but extract failed; retrying without proxy...')
                    ydl_opts.pop('proxy', None)
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=True)
                            extract_exception = None
                    except Exception as e2:
                        extract_exception = e2
                        app.logger.exception('Retry (no proxy after validated proxy) failed: %s', e2)

        if extract_exception:
            # Last resort: if cookies were provided, try forcing cookiefile into ydl_opts and retry once more
            if cookies_file and os.path.isfile(cookies_file):
                app.logger.warning('Attempting final extract_info retry using cookies only...')
                ydl_opts.pop('proxy', None)
                ydl_opts['cookiefile'] = cookies_file
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        extract_exception = None
                except Exception as e3:
                    extract_exception = e3
                    app.logger.exception('Final retry (cookies only) failed: %s', e3)

        # If extract_info fails and returns None or throws, avoid calling .get on it
        if extract_exception or not (info := locals().get('info')):
            app.logger.error('yt-dlp.extract_info returned no info for URL: %s', url)
            # Log any temp candidates to help debugging
            temp_candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
            cwd_candidates = glob.glob(os.path.join(os.path.abspath('.'), '**', f"{temp_filename}*"), recursive=True)
            app.logger.error('Temp candidates: %s; Cwd candidates: %s', temp_candidates, cwd_candidates)
            # Provide a helpful error message to the user
            if extract_exception:
                msg = str(extract_exception)
                if 'proxy' in msg.lower() or 'tunnel' in msg.lower():
                    return None, 'Proxy connection failed; please remove proxy or try a working proxy.'
                if '403' in msg:
                    return None, '403 Forbidden from YouTube. Try uploading browser cookies or try from a different network (VPN).'
                return None, f'yt-dlp failed to extract video information: {msg}'
            return None, 'yt-dlp failed to extract video information. Check server logs for details.'

        # Log what was extracted
        app.logger.debug(f"Download successful! Listing all files in {TEMP_DIR}")
        all_files = os.listdir(TEMP_DIR)
        app.logger.debug(f"All files in temp dir: {all_files}")
        
        temp_candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
        app.logger.debug(f"Candidates matching {temp_filename}: {temp_candidates}")

        # Normalise info to a dict-like object to avoid AttributeError on .get
        info_dict = info if isinstance(info, dict) else {}

        # Debug: log info summary and any files that match the temp filename
        try:
            app.logger.debug("yt-dlp info type: %s; keys: %s", type(info), list(info_dict.keys()) if isinstance(info_dict, dict) else '')
        except Exception:
            app.logger.debug("yt-dlp info: (unable to list keys)")
        temp_candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
        app.logger.debug("Temp dir candidates after extraction: %s", temp_candidates)
        cwd_candidates = glob.glob(os.path.join(os.path.abspath('.'), '**', f"{temp_filename}*"), recursive=True)
        app.logger.debug("Cwd candidates after extraction: %s", cwd_candidates)

        if subs_only:
            rate_limited = False
            # Prefer explicit requested subtitles, then 'subtitles', then automatic captions
            for key in ('requested_subtitles', 'subtitles', 'automatic_captions'):
                subs_sources = info_dict.get(key) or {}
                # Prefer English first, then try Hindi (auto-generated) and translate
                url, ext = _find_subtitle_url(subs_sources, 'en')
                lang_downloaded = 'en' if url else None
                if not url:
                    url, ext = _find_subtitle_url(subs_sources, 'hi')
                    lang_downloaded = 'hi' if url else lang_downloaded

                if url:
                    try:
                        resp = _get_with_retries(url, session=session, proxies=proxies)
                        if resp is None:
                            rate_limited = True
                            continue
                        ext = (ext or 'vtt').lower()
                        sub_path = os.path.join(TEMP_DIR, f"{temp_filename}.en.{ext}")

                        # Treat common subtitle formats as text
                        if ext in ('vtt', 'srt', 'txt', 'json3', 'ttml'):
                            text = resp.text
                            # If not English and translator available, try to translate
                            if lang_downloaded and lang_downloaded != 'en' and HAS_TRANSLATOR:
                                try:
                                    translated = GoogleTranslator(source='auto', target='en').translate(text)
                                    with open(sub_path, 'w', encoding='utf-8') as fh:
                                        fh.write(translated)
                                    app.logger.info("Downloaded and translated subtitle (%s -> en): %s", key, sub_path)
                                    return sub_path, info_dict.get('title', 'subtitles')
                                except Exception as te:
                                    app.logger.exception("Failed to translate subtitle: %s", te)
                                    # fallback to raw text
                                    with open(sub_path, 'w', encoding='utf-8') as fh:
                                        fh.write(text)
                                    return sub_path, info_dict.get('title', 'subtitles')
                            else:
                                with open(sub_path, 'w', encoding='utf-8') as fh:
                                    fh.write(text)
                                app.logger.info("Wrote subtitle file from %s metadata: %s", key, sub_path)
                                return sub_path, info_dict.get('title', 'subtitles')
                        else:
                            # Binary write
                            with open(sub_path, 'wb') as fh:
                                fh.write(resp.content)
                            app.logger.info("Wrote subtitle file from %s metadata: %s", key, sub_path)
                            return sub_path, info_dict.get('title', 'subtitles')

                    except requests.exceptions.HTTPError as he:
                        status = None
                        try:
                            status = he.response.status_code
                        except Exception:
                            status = None
                        if status == 429:
                            app.logger.warning("Rate limited while fetching subtitles (%s): %s", key, he)
                            rate_limited = True
                            continue
                        app.logger.exception("Failed to download subtitle from metadata (%s): %s", key, he)
                    except Exception as e:
                        app.logger.exception("Failed to download subtitle from metadata (%s): %s", key, e)

            # If metadata download failed, search for generated subtitle files in TEMP_DIR
            found = None
            for pattern in (f"{temp_filename}*.en.vtt", f"{temp_filename}*.en.srt", f"{temp_filename}*.vtt", f"{temp_filename}*.srt"):
                matches = glob.glob(os.path.join(TEMP_DIR, pattern))
                if matches:
                    found = matches[0]
                    break
            if found and os.path.isfile(found):
                return found, info_dict.get('title', 'subtitles')

            # If we were rate limited while fetching metadata, inform the user
            if rate_limited:
                return None, "Subtitle downloads are being rate-limited by YouTube (HTTP 429). Try again later."

            # As a last resort, try YouTube Transcript API (can fetch generated transcripts and translate them)
            if not HAS_YT_TRANSCRIPT_API:
                temp_candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
                cwd_candidates = glob.glob(os.path.join(os.path.abspath('.'), '**', f"{temp_filename}*"), recursive=True)
                all_candidates = temp_candidates + cwd_candidates
                readable = ', '.join([os.path.basename(x) for x in all_candidates]) or 'none'
                if all_candidates:
                    return None, f"Subtitles requested but file not found on disk; candidates: {readable}"
                return None, "No English subtitles found for this video. To enable transcript-based fallbacks, install 'youtube-transcript-api' (and 'deep-translator' to auto-translate generated captions)."

            # Try to fetch a transcript (prefer English, then Hindi) using youtube-transcript-api
            vid = _extract_youtube_id(url)
            if not vid:
                return None, "No subtitles found and unable to determine video id for transcript fallback."

            try:
                transcript = None
                transcript_lang = None
                # First try to get an English transcript
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(vid, languages=['en'])
                    transcript_lang = 'en'
                except Exception as e_en:
                    app.logger.debug("No direct English transcript: %s", e_en)
                    # Next try to fetch Hindi transcript (commonly auto-generated)
                    try:
                        transcript = YouTubeTranscriptApi.get_transcript(vid, languages=['hi'])
                        transcript_lang = 'hi'
                    except Exception as e_hi:
                        app.logger.debug("No Hindi transcript via get_transcript: %s", e_hi)
                        transcript = None
                        transcript_lang = None

                if transcript:
                    # If transcript is not English and translator is available, translate segment by segment
                    if transcript_lang and transcript_lang != 'en' and HAS_TRANSLATOR:
                        try:
                            for seg in transcript:
                                try:
                                    seg['text'] = GoogleTranslator(source='auto', target='en').translate(seg.get('text', ''))
                                except Exception as te:
                                    app.logger.exception('Translation error for segment: %s', te)
                            app.logger.info('Translated transcript segments to English')
                        except Exception as trans_e:
                            app.logger.exception('Failed to translate transcript: %s', trans_e)

                    sub_path = os.path.join(TEMP_DIR, f"{temp_filename}.en.vtt")
                    _write_transcript_vtt(transcript, sub_path)
                    return sub_path, info_dict.get('title', 'subtitles')
                else:
                    return None, "No English subtitles/transcripts available for this video."
            except Exception as e:
                app.logger.exception("Transcript fallback error: %s", e)
                return None, "Transcript fallback failed; check server logs for details."
            # If a playlist, download all videos
            if isinstance(info, dict) and 'entries' in info:
                downloaded_files = []
                for entry in info['entries']:
                    # Skip DRM protected or unavailable videos
                    if entry is None or entry.get('is_live') or entry.get('drm_family'):
                        continue
                    file_path = ydl.prepare_filename(entry)
                    if audio_only:
                        file_path = os.path.splitext(file_path)[0] + ".mp3"
                    # If file not present, try to find a matched candidate
                    if not os.path.isfile(file_path):
                        candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
                        for c in candidates:
                            if os.path.isfile(c):
                                file_path = c
                                break
                    downloaded_files.append((file_path, entry.get('title', 'downloaded_file')))
                if not downloaded_files:
                    return None, "No downloadable videos found in playlist."
                # Return first file for browser download, but you can customize to zip all
                first_file = downloaded_files[0][0]
                if not os.path.isfile(first_file):
                    # search for candidates
                    candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
                    cwd_candidates = glob.glob(os.path.join(os.path.abspath('.'), '**', f"{temp_filename}*"), recursive=True)
                    all_candidates = candidates + cwd_candidates
                    app.logger.error("Playlist first file missing; candidates: %s", all_candidates)
                    readable = ', '.join([os.path.basename(x) for x in all_candidates]) or 'none'
                    return None, f"Downloaded file not found. Files found: {readable}"
                return first_file, downloaded_files[0][1]
            else:
                downloaded_file = ydl.prepare_filename(info)
                if audio_only:
                    downloaded_file = os.path.splitext(downloaded_file)[0] + ".mp3"

                app.logger.debug(f"Prepared filename: {downloaded_file}, Temp dir: {TEMP_DIR}")

                # Ensure file exists; try to locate by temp filename if not present
                if not os.path.isfile(downloaded_file):
                    app.logger.debug(f"Prepared file not found at {downloaded_file}, searching in temp dir...")
                    candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
                    app.logger.debug(f"Found candidates: {candidates}")
                    for c in candidates:
                        if os.path.isfile(c):
                            app.logger.debug(f"Using candidate: {c}")
                            downloaded_file = c
                            break

                if not os.path.isfile(downloaded_file):
                    # Try searching recursively in the workspace for any matching candidates
                    cwd_candidates = glob.glob(os.path.join(os.path.abspath('.'), '**', f"{temp_filename}*"), recursive=True)
                    candidates = glob.glob(os.path.join(TEMP_DIR, f"{temp_filename}*"))
                    all_candidates = candidates + cwd_candidates
                    app.logger.error("Downloaded file missing; candidates: %s", all_candidates)
                    readable = ', '.join([os.path.basename(x) for x in all_candidates]) or 'none'
                    return None, f"Downloaded file not found. Files found: {readable}"

                return downloaded_file, info_dict.get('title', 'downloaded_file')
    except Exception as e:
        app.logger.exception("Download error")
        return None, f"Error during download: {e}"

<<<<<<< HEAD
=======

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
>>>>>>> 793ed659df8cb1b901b8470ef1f4158f973b4d84


@app.route('/downloads')
def list_downloads():
    """List all available downloads in temp folder"""
    try:
        files = []
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath) and not filename.endswith(('.part', '.ytdl', '.info.json')):
                files.append({
                    'name': filename,
                    'size': os.path.getsize(filepath),
                    'url': f'/download-file/{filename}'
                })
        return {'files': files}
    except Exception as e:
        return {'error': str(e)}, 400

@app.route('/download-file/<filename>')
def download_file(filename):
    """Download a file from temp folder"""
    try:
        filepath = os.path.join(TEMP_DIR, filename)
        
        # Security check - prevent directory traversal
        if not os.path.abspath(filepath).startswith(os.path.abspath(TEMP_DIR)):
            return "Invalid file", 403
            
        if not os.path.isfile(filepath):
            return "File not found", 404
            
        mimetype, _ = mimetypes.guess_type(filepath)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype or 'application/octet-stream'
        )
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    """Fetch video info and thumbnail from YouTube"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        
        if not url:
            return {'error': 'No URL provided'}, 400
        
        # Extract video info using yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        return {
            'title': info.get('title', 'Unknown Title'),
            'description': info.get('description', '')[:150],  # First 150 chars
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0)
        }
    except Exception as e:
        return {'error': str(e)}, 400


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
        quality = request.form.get('quality') or None

<<<<<<< HEAD
        # Basic URL validation to avoid accidental invalid inputs (like running commands)
        if not (url.startswith('http://') or url.startswith('https://')):
            return render_template("index.html", error='Please enter a valid http or https URL.')

        # Handle optional cookies upload and proxy
        cookies_path = None
        cookies_file = request.files.get('cookies_file')
        if cookies_file and getattr(cookies_file, 'filename', ''):
            cookies_path = os.path.join(TEMP_DIR, f"cookies_{uuid.uuid4().hex}.txt")
            cookies_file.save(cookies_path)

        proxy = request.form.get('proxy') or None

        try:
            _res = download_video_to_file(url, audio_only, subs_only, cookies_file=cookies_path, proxy=proxy, quality=quality)
            if not (isinstance(_res, tuple) and len(_res) == 2):
                app.logger.error("download_video_to_file returned unexpected result: %r", _res)
                return render_template("index.html", error="Internal server error during download. Check server logs.")
            file_path, title_or_error = _res
        except Exception as e:
            app.logger.exception("Error during download")
            return render_template("index.html", error=f"Download error: {str(e)[:100]}")

        # If cookies file was saved but not used or an error occurred, ensure it's cleaned up later in cleanup if set
        if cookies_path and not file_path:
            try:
                if os.path.exists(cookies_path):
                    os.remove(cookies_path)
            except Exception:
                pass

=======
        file_path, title_or_error = download_video_to_file(url, audio_only, subs_only)
        
>>>>>>> 793ed659df8cb1b901b8470ef1f4158f973b4d84
        if file_path:
            if not os.path.isfile(file_path):
                app.logger.error(f"File does not exist: {file_path}")
                return render_template("index.html", error=f"File not found: {os.path.basename(file_path)}")

            # Don't delete file immediately - let it stay in temp for network access
            # Just send it without cleanup
            mimetype, _ = mimetypes.guess_type(file_path)
            if subs_only:
                mimetype = mimetype or 'text/vtt'
            elif audio_only:
                mimetype = mimetype or 'audio/mpeg'
            else:
                mimetype = mimetype or 'application/octet-stream'

            return send_file(
                file_path,
                as_attachment=True,
                download_name=os.path.basename(file_path),
                mimetype=mimetype
            )
        else:
            return render_template("index.html", error=title_or_error)

    return render_template("index.html")


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
    app.run(host='0.0.0.0', port=5000, debug=True)
