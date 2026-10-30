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
# 1. Download Cyber B-Roll (Contextual to Scam Threat)
# -------------------------------------------------------------
def fetch_cyber_broll(query, output_filename):
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return False

    url = "https://pixabay.com/api/videos/"
    params = {
        "key": api_key,
        "q": query,
        "video_type": "film",
        "per_page": 8,
        "safesearch": "true"
    }

    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code == 200:
            hits = res.json().get("hits", [])
            if hits:
                random.shuffle(hits)
                for hit in hits:
                    vids = hit.get("videos", {})
                    target = vids.get("large") or vids.get("medium") or vids.get("small")
                    if target and target.get("url"):
                        with requests.get(target["url"], stream=True, timeout=40) as r:
                            r.raise_for_status()
                            with open(output_filename, "wb") as f:
                                for chunk in r.iter_content(chunk_size=16384):
                                    f.write(chunk)
                        return True
    except Exception as e:
        print(f"B-roll fetch notice for {query}: {e}")
    return False

# -------------------------------------------------------------
# 2. Audio & Compact Middle Subtitle Generator (20% Middle)
# -------------------------------------------------------------
def ms_to_ass(ms):
    cs = int((ms % 1000) / 10)
    total_sec = int(ms / 1000)
    s = total_sec % 60
    m = int(total_sec / 60) % 60
    h = int(total_sec / 3600)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

async def render_dialogue_audio(dialogue_list):
    voices = {
        "Maya": "en-US-JennyNeural",
        "Vikram": "en-US-ChristopherNeural"
    }

    # ASS Header: Alignment=5 is Dead-Center (x=540, y=960).
    # Fontsize=32 with tight margins makes it occupy only ~20% of the screen center.
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MayaMid,DejaVu Sans,32,&H00FFFFFF,&H0000FFFF,&H00000000,&HA0000000,1,0,0,0,100,100,1,0,3,3,1,5,180,180,0,1
Style: VikramMid,DejaVu Sans,32,&H00FFFFFF,&H0000FFFF,&H00000000,&HA0000000,1,0,0,0,100,100,1,0,3,3,1,5,180,180,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    line_audio_files = []
    current_time_ms = 0
    line_durations = []

    for idx, item in enumerate(dialogue_list):
        speaker = item.get("speaker", "Maya")
        text = item.get("text", "")
        voice = voices.get(speaker, "en-US-ChristopherNeural")

        line_file = f"line_{idx}.mp3"
        line_audio_files.append(line_file)

        communicate = edge_tts.Communicate(text, voice, rate="+4%", pitch="-1Hz")
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
        line_durations.append((line_duration_sec, speaker))

        style_name = "MayaMid" if speaker == "Maya" else "VikramMid"
        tag_color = "\\c&H00A5F5&" if speaker == "Maya" else "\\c&H00E996&"

        # Chunk into small 2-3 word segments for high kinetic readability
        srt_content = submaker.get_srt().strip()
        blocks = re.split(r'\n\s*\n', srt_content) if srt_content else []

        words_data = []
        for b in blocks:
            lines = b.split('\n')
            if len(lines) >= 3:
                time_line = lines[1]
                word = " ".join(lines[2:]).strip().upper()
                m = re.match(r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)', time_line)
                if m:
                    g = [int(x) for x in m.groups()]
                    w_start = current_time_ms + (g[0]*3600000 + g[1]*60000 + g[2]*1000 + g[3])
                    w_end = current_time_ms + (g[4]*3600000 + g[5]*60000 + g[6]*1000 + g[7])
                    words_data.append((w_start, w_end, word))

        if words_data:
            chunk_size = 3
            for i in range(0, len(words_data), chunk_size):
                chunk = words_data[i:i + chunk_size]
                c_start = chunk[0][0]
                c_end = max(chunk[-1][1], c_start + 400)
                phrase = " ".join([w[2] for w in chunk])
                dialogue_text = f"{{{tag_color}\\fs24\\b1}}[{speaker.upper()}]\\N{{\\r{style_name}\\fs34\\b1}}{phrase}"
                events.append(f"Dialogue: 0,{ms_to_ass(c_start)},{ms_to_ass(c_end)},{style_name},,0,0,0,,{dialogue_text}")
        else:
            words = text.upper().split()
            chunk_size = 3
            num_chunks = max(1, len(words) // chunk_size)
            chunk_dur = line_duration_ms // num_chunks
            for i in range(0, len(words), chunk_size):
                sub_words = " ".join(words[i:i + chunk_size])
                w_start = current_time_ms + (i // chunk_size) * chunk_dur
                w_end = min(current_time_ms + line_duration_ms, w_start + chunk_dur)
                dialogue_text = f"{{{tag_color}\\fs24\\b1}}[{speaker.upper()}]\\N{{\\r{style_name}\\fs34\\b1}}{sub_words}"
                events.append(f"Dialogue: 0,{ms_to_ass(w_start)},{ms_to_ass(w_end)},{style_name},,0,0,0,,{dialogue_text}")

        current_time_ms += line_duration_ms

    with open("audio_concat.txt", "w") as f:
        for a in line_audio_files:
            f.write(f"file '{a}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio_concat.txt", "-c", "copy", "dialogue_master.mp3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open("subtitles.ass", "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return current_time_ms / 1000.0, line_durations

# -------------------------------------------------------------
# 3. Assemble Video with Guaranteed B-Roll & Centered Subtitles
# -------------------------------------------------------------
def assemble_cinematic_short(video_clips, total_duration, output_video="scam_short.mp4"):
    clip_dur = total_duration / len(video_clips)

    prepared_clips = []
    for idx, raw_clip in enumerate(video_clips):
        processed_clip = f"prep_{idx}.mp4"
        prepared_clips.append(processed_clip)
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "3", "-i", raw_clip,
            "-t", f"{clip_dur:.2f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
                   "eq=contrast=1.12:saturation=1.15:brightness=-0.04,vignette=PI/4.5,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
            processed_clip
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open("clips.txt", "w") as f:
        for c in prepared_clips:
            f.write(f"file '{c}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "clips.txt", "-c", "copy", "base_video.mp4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    ambient_path = "assets/ambient.mp3"
    has_ambient = os.path.exists(ambient_path)

    if has_ambient:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "base_video.mp4",
            "-i", "dialogue_master.mp3",
            "-stream_loop", "-1", "-i", ambient_path,
            "-filter_complex",
            "[0:v]ass=subtitles.ass[vfinal];[2:a]volume=0.10[bg];[1:a][bg]amix=inputs=2:duration=first[afinal]",
            "-map", "[vfinal]", "-map", "[afinal]",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]
    else:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "base_video.mp4",
            "-i", "dialogue_master.mp3",
            "-vf", "ass=subtitles.ass",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]

    subprocess.run(cmd_final, check=True)
    print("Short assembled successfully with small middle subtitles!")

# -------------------------------------------------------------
# 4. YouTube Upload Handler
# -------------------------------------------------------------
def upload_to_youtube(video_path, title, description):
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube tokens not configured in GitHub Secrets. Skipping upload.")
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
                "description": (
                    f"{description}\n\n"
                    f"🛡️ Live Cyber Threat Matrix & SOP Protocols:\n"
                    f"https://santoshtiru1.github.io/Scam-Alerts/\n\n"
                    f"#CyberSecurity #Investigation #ScamAlert #Shorts"
                ),
                "tags": ["CyberSecurity", "Investigation", "ScamAlert", "Shorts"],
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
        print("SUCCESS: Published Short! Video ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload notice (non-fatal): {e}")

# -------------------------------------------------------------
# 5. Pipeline Orchestrator
# -------------------------------------------------------------
def process_youtube_short(day_entry, story):
    if not story or "dialogue" not in story:
        print("Invalid dialogue story structure passed.")
        return

    # Verified cyber threat visual queries that never return lipstick or beaches
    queries = [
        "hacker coding dark room",
        "cyber security network data",
        "smartphone screen scam hacking",
        "police emergency lights night"
    ]

    video_clips = []
    print("Step 1: Downloading verified cybercrime b-roll...")
    for idx, q in enumerate(queries):
        clip = f"clip_{idx}.mp4"
        if fetch_cyber_broll(q, clip):
            video_clips.append(clip)

    fallbacks = ["digital code matrix", "dark tech server", "mobile phone notification dark", "cyber attack danger"]
    fb_idx = 0
    while len(video_clips) < 4 and fb_idx < len(fallbacks):
        clip = f"fb_clip_{fb_idx}.mp4"
        if fetch_cyber_broll(fallbacks[fb_idx], clip):
            video_clips.append(clip)
        fb_idx += 1

    if not video_clips:
        print("No stock footage available. Skipping video build.")
        return

    print("Step 2: Synthesizing character dialogue & small middle subtitles...")
    total_dur, line_durations = asyncio.run(render_dialogue_audio(story["dialogue"]))

    print("Step 3: Assembling video with centered 20% typography...")
    assemble_cinematic_short(video_clips, total_dur)

    full_transcript = " ".join([f"{item['speaker']}: {item['text']}" for item in story["dialogue"]])
    print("Step 4: Uploading to YouTube...")
    upload_to_youtube("scam_short.mp4", story.get("title", "Cyber Threat Investigation"), full_transcript)
