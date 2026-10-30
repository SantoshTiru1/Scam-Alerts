import os
import re
import json
import random
import asyncio
import subprocess
import requests
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -------------------------------------------------------------
# 1. Download Verified Presenter Clips (Maya & Vikram)
# -------------------------------------------------------------
def ensure_presenter_clips():
    """
    Downloads and prepares verified 1080x1920 portrait clips of:
    - Maya: Professional female presenter speaking directly to camera
    - Vikram: Professional male presenter speaking directly to camera
    """
    os.makedirs("assets", exist_ok=True)
    maya_path = "assets/maya_presenter.mp4"
    vikram_path = "assets/vikram_presenter.mp4"

    api_key = os.getenv("PIXABAY_API_KEY")

    # High-relevance verified search queries with orientation=vertical filter
    presenters = [
        (maya_path, "woman speaking to camera portrait interview"),
        (vikram_path, "man speaking to camera interview portrait")
    ]

    for path, query in presenters:
        if not os.path.exists(path) and api_key:
            print(f"Downloading verified presenter footage for: {path}...")
            try:
                url = "https://pixabay.com/api/videos/"
                params = {
                    "key": api_key,
                    "q": query,
                    "video_type": "film",
                    "per_page": 10,
                    "safesearch": "true"
                }
                res = requests.get(url, params=params, timeout=20)
                if res.status_code == 200:
                    hits = res.json().get("hits", [])
                    chosen_url = None
                    for hit in hits:
                        vids = hit.get("videos", {})
                        target = vids.get("large") or vids.get("medium") or vids.get("small")
                        if target and target.get("url"):
                            chosen_url = target["url"]
                            break

                    if chosen_url:
                        raw_temp = f"raw_{os.path.basename(path)}"
                        with requests.get(chosen_url, stream=True, timeout=60) as r:
                            r.raise_for_status()
                            with open(raw_temp, "wb") as f:
                                for chunk in r.iter_content(chunk_size=16384):
                                    f.write(chunk)

                        # Scale and center-crop to 1080x1920 30fps
                        cmd = [
                            "ffmpeg", "-y", "-i", raw_temp,
                            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                            path
                        ]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                        if os.path.exists(raw_temp):
                            os.remove(raw_temp)
                        print(f"✓ Saved portrait presenter: {path}")
            except Exception as e:
                print(f"Notice downloading {path}: {e}")

# -------------------------------------------------------------
# 2. Audio & Clean 3-4 Word Chunk Subtitles
# -------------------------------------------------------------
def ms_to_srt_time(ms):
    total_sec = int(ms / 1000)
    s = total_sec % 60
    m = int(total_sec / 60) % 60
    h = int(total_sec / 3600)
    millis = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"

async def render_dialogue_audio(dialogue_list):
    voices = {
        "Maya": "en-US-JennyNeural",
        "Vikram": "en-US-ChristopherNeural"
    }

    srt_entries = []
    line_audio_files = []
    current_time_ms = 0
    line_segments = []
    srt_counter = 1

    for idx, item in enumerate(dialogue_list):
        speaker = item.get("speaker", "Maya")
        text = item.get("text", "")
        voice = voices.get(speaker, "en-US-ChristopherNeural")

        line_file = f"line_{idx}.mp3"
        line_audio_files.append(line_file)

        communicate = edge_tts.Communicate(text, voice, rate="+3%", pitch="-1Hz")
        submaker = edge_tts.SubMaker()

        with open(line_file, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)

        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", line_file]
        dur_res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        line_duration_sec = float(dur_res.stdout.strip())
        line_duration_ms = int(line_duration_sec * 1000)

        line_segments.append((line_file, line_duration_sec, speaker))
        tag_color = "#F59E0B" if speaker == "Maya" else "#0EA5E9"

        # Group words into clean 3-to-4 word phrases so they don't flood the screen
        srt_content = submaker.get_srt().strip()
        blocks = re.split(r'\n\s*\n', srt_content) if srt_content else []

        words_data = []
        for b in blocks:
            lines = b.split('\n')
            if len(lines) >= 3:
                time_line = lines[1]
                word = " ".join(lines[2:]).strip()
                m = re.match(r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)', time_line)
                if m:
                    g = [int(x) for x in m.groups()]
                    w_start = current_time_ms + (g[0]*3600000 + g[1]*60000 + g[2]*1000 + g[3])
                    w_end = current_time_ms + (g[4]*3600000 + g[5]*60000 + g[6]*1000 + g[7])
                    words_data.append((w_start, w_end, word))

        if words_data:
