import os
import re
import json
import asyncio
import subprocess
import requests
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -------------------------------------------------------------
# 1. Fetch Real Video Footage via Pixabay Video API
# -------------------------------------------------------------
def fetch_pixabay_video(query, output_filename):
    """
    Finds and downloads a real stock video clip using the free Pixabay API.
    """
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        print("PIXABAY_API_KEY is missing in GitHub Secrets.")
        return False

    url = "https://pixabay.com/api/videos/"
    params = {
        "key": api_key,
        "q": query,
        "video_type": "all",
        "per_page": 5,
        "safesearch": "true"
    }

    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code == 200:
            hits = res.json().get("hits", [])
            for hit in hits:
                videos = hit.get("videos", {})
                # Look for medium or large clip
                target = videos.get("medium") or videos.get("large") or videos.get("small")
                if target and target.get("url"):
                    video_url = target.get("url")
                    v_res = requests.get(video_url, timeout=45)
                    if v_res.status_code == 200:
                        with open(output_filename, "wb") as f:
                            f.write(v_res.content)
                        print(f"Downloaded Pixabay footage for '{query}': {output_filename}")
                        return True
        print(f"No video hit on Pixabay for '{query}'.")
    except Exception as e:
        print(f"Pixabay fetch error: {e}")
    return False

# -------------------------------------------------------------
# 2. Voiceover & Aligned Karaoke Subtitles (.ass)
# -------------------------------------------------------------
def ms_to_ass_time(ms):
    cs = int((ms % 1000) / 10)
    total_sec = int(ms / 1000)
    s = total_sec % 60
    total_min = int(total_sec / 60)
    m = total_min % 60
    h = int(total_min / 60)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

async def generate_narration_and_subtitles(text, audio_path="scam_audio.mp3", ass_path="subtitles.ass"):
    """
    Generates human-like Edge-TTS speech with synchronized ASS subtitles.
    """
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="-2%", pitch="-2Hz")
    submaker = edge_tts.SubMaker()

    with open(audio_path, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    srt_text = submaker.get_srt()

    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,64,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,920,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    blocks = re.split(r'\n\s*\n', srt_text.strip())
    for b in blocks:
        lines = b.split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            content = " ".join(lines[2:]).strip().upper()
            m = re.match(r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)', time_line)
            if m:
                g = [int(x) for x in m.groups()]
                start_ms = g[0]*3600000 + g[1]*60000 + g[2]*1000 + g[3]
                end_ms = g[4]*3600000 + g[5]*60000 + g[6]*1000 + g[7]
                if end_ms - start_ms < 320:
                    end_ms = start_ms + 320

                start_str = ms_to_ass_time(start_ms)
                end_str = ms_to_ass_time(end_ms)
                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{content}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")
    print("Voiceover & Subtitles ready.")

def get_duration(file_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 50.0

# -------------------------------------------------------------
# 3. Stitch Video Clips & Burn Subtitles with Native FFmpeg
# -------------------------------------------------------------
def assemble_final_short(video_clips, audio_file="scam_audio.mp3", ass_file="subtitles.ass", output_video="scam_short.mp4"):
    total_audio_duration = get_duration(audio_file)
    clip_dur = total_audio_duration / len(video_clips)

    prepared_clips = []
    for idx, raw_clip in enumerate(video_clips):
        processed_clip = f"prep_{idx}.mp4"
        prepared_clips.append(processed_clip)
        # Scale & center-crop to 1080x1920 (9:16 portrait) at 30fps
        cmd_prep = [
            "ffmpeg", "-y",
            "-stream_loop", "3",
            "-i", raw_clip,
            "-t", f"{clip_dur:.2f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
            processed_clip
        ]
        subprocess.run(cmd_prep, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open("clips_list.txt", "w") as f:
        for c in prepared_clips:
            f.write(f"file '{c}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", "clips_list.txt",
        "-c", "copy", "visual_base.mp4"
    ]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    ambient_path = "assets/ambient.mp3" if os.path.exists("assets/ambient.mp3") else "ambient.mp3"
    has_ambient = os.path.exists(ambient_path)

    if has_ambient:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "visual_base.mp4",
            "-i", audio_file,
            "-stream_loop", "-1", "-i", ambient_path,
            "-filter_complex",
            f"[0:v]ass={ass_file}[v];[2:a]volume=0.10[bg];[1:a][bg]amix=inputs=2:duration=first[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]
    else:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "visual_base.mp4",
            "-i", audio_file,
            "-vf", f"ass={ass_file}",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]

    subprocess.run(cmd_final, check=True)
    print("Video assembled with stock footage, audio mix, and subtitles.")

# -------------------------------------------------------------
# 4. YouTube Upload Handler
# -------------------------------------------------------------
def upload_to_youtube(video_path, title, script):
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube secrets not set. Skipping upload.")
        return

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": f"⚠️ {title[:65]} #Shorts",
                "description": f"{script}\n\n🛡️ Real-time cyber threat monitor:\nhttps://santoshtiru1.github.io/Scam-Alerts/\n\n#CyberSecurity #ScamAlert #TrueCrime #Shorts",
                "tags": ["CyberSecurity", "ScamAlert", "TrueCrime", "Shorts"],
                "categoryId": "28"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        res = request.execute()
        print("SUCCESS: Published to YouTube! Video ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload notice (non-fatal): {e}")

# -------------------------------------------------------------
# 5. Pipeline Entry Point
# -------------------------------------------------------------
def process_youtube_short(day_entry, story):
    if not story or "voiceover" not in story:
        print("Invalid story data passed.")
        return

    search_queries = story.get("video_queries", ["technology hacker", "smartphone dark", "cyber attack", "digital code"])

    video_clips = []
    print("Step 1: Downloading footage from Pixabay...")
    for idx, q in enumerate(search_queries):
        clip_name = f"source_{idx}.mp4"
        if fetch_pixabay_video(q, clip_name):
            video_clips.append(clip_name)

    # Reliable fallback queries if specific terms yielded nothing
    fallbacks = ["hacker", "technology", "computer code", "network"]
    fb_idx = 0
    while len(video_clips) < 4 and fb_idx < len(fallbacks):
        clip_name = f"fb_{fb_idx}.mp4"
        if fetch_pixabay_video(fallbacks[fb_idx], clip_name):
            video_clips.append(clip_name)
        fb_idx += 1

    if not video_clips:
        print("Could not retrieve video clips. Skipping.")
        return

    print("Step 2: Synthesizing voiceover and generating subtitles...")
    asyncio.run(generate_narration_and_subtitles(story["voiceover"]))

    print("Step 3: Assembling vertical Short...")
    assemble_final_short(video_clips)

    print("Step 4: Uploading to YouTube...")
    upload_to_youtube("scam_short.mp4", story.get("title", "Cyber Threat Alert"), story["voiceover"])
