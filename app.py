from flask import Flask, request, render_template, render_template_string, send_file, after_this_request, jsonify, url_for
import os
import glob
import mimetypes
import requests
import time
import http.cookiejar as cookiejar
import shutil
import threading
import uuid
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

app = Flask(__name__)

TEMP_DIR = os.path.abspath('temp_downloads')
os.makedirs(TEMP_DIR, exist_ok=True)

# Resolve ffmpeg location in a cross-platform way. Prefer system ffmpeg if available,
# otherwise fall back to a local ./ffmpeg.exe (keeps compatibility with the repo's
# Windows binary). If neither exists, leave as None so yt-dlp can try defaults.
FFMPEG_LOCATION = shutil.which('ffmpeg') or (os.path.abspath('./ffmpeg.exe') if os.path.exists(os.path.abspath('./ffmpeg.exe')) else None)

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

def download_video_to_file(url, audio_only=False, subs_only=False, cookies_file=None, proxy=None, quality=None, progress_hook=None):
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
            if FFMPEG_LOCATION:
                ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            if proxy:
                ydl_opts['proxy'] = proxy
        elif audio_only:
            ydl_format = 'bestaudio[ext=m4a]/bestaudio/best'
            postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            ydl_opts = {
                'format': ydl_format,
                'outtmpl': output_template,
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
            if FFMPEG_LOCATION:
                ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
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
                'quiet': True,
                'postprocessors': postprocessors,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'extract_flat': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            if FFMPEG_LOCATION:
                ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
            if proxy:
                ydl_opts['proxy'] = proxy
        
        if progress_hook:
            ydl_opts['progress_hooks'] = [progress_hook]
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
            else: # If proxy was set but validation succeeded earlier, still try fallback without proxy
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
                    app.logger.exception('Retry (cookies only) failed: %s', e3)

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
                                    app.logger.exception('Failed to translate subtitle: %s', te)
                                    # fallback to raw text
                                    with open(sub_path, 'w', encoding='utf-8') as fh:
                                        fh.write(text)
                                    return sub_path, info_dict.get('title', 'subtitles')
                            else:
                                with open(sub_path, 'w', encoding='utf-8') as fh:
                                    fh.write(text)
                                return sub_path, info_dict.get('title', 'subtitles')
                        else: # Binary write
                            with open(sub_path, 'wb') as fh:
                                fh.write(resp.content)
                            return sub_path, info_dict.get('title', 'subtitles')

                    except requests.exceptions.HTTPError as he:
                        status = None
                        try:
                            status = he.response.status_code
                        except Exception:
                            status = None
                        if status == 429:
                            rate_limited = True
                            continue
                        app.logger.exception('Failed to download subtitle from metadata (%s): %s', key, he)
                    except Exception as e:
                        app.logger.exception('Failed to download subtitle from metadata (%s): %s', key, e)

            # If metadata download failed, search for generated subtitle files in TEMP_DIR
            found = None
            for pattern in (f"{temp_filename}.en.vtt", f"{temp_filename}.en.srt", f"{temp_filename}.vtt", f"{temp_filename}.srt"):
                matches = glob.glob(os.path.join(TEMP_DIR, pattern))
                if matches:
                    found = matches[0]
                    break
            if found and os.path.isfile(found):
                return found, info_dict.get('title', 'subtitles')

            # If we were rate limited while fetching metadata, inform the user
            if rate_limited:
                return None, "Subtitle downloads are being rate-limited by YouTube (HTTP 429). Try again later."

            # If no subtitles found via metadata, try YouTube Transcript API
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
                app.logger.exception('Transcript fallback error: %s', e)
                return None, "Transcript fallback failed; check server logs for details."
    except Exception as e:
        app.logger.exception('Final catch in download_video_to_file: %s', e)
        return None, f'An unexpected error occurred: {e}'

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)