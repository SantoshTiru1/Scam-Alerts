import os
import re
import json
import random
import asyncio
import subprocess
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -------------------------------------------------------------
# 1. Avatars & Character Card Generator
# -------------------------------------------------------------
def ensure_character_avatars():
    """Generates clean circular character badges if custom assets aren't in assets/."""
    os.makedirs("assets", exist_ok=True)
    
    characters = [
        ("assets/vikram.png", "VIKRAM", "CYBER INTEL", (14, 165, 233)), # Cyan
        ("assets/maya.png", "MAYA", "INVESTIGATOR", (245, 158, 11))      # Amber
    ]
    
    for path, name, role, color in characters:
        if not os.path.exists(path):
            img = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Outer circular badge with glow
            draw.ellipse([(10, 10), (230, 230)], fill=(15, 23, 42, 230), outline=color, width=6)
            draw.ellipse([(25, 25), (215, 215)], outline=(255, 255, 255, 160), width=2)
            
            try:
                font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
                font_role = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            except Exception:
                font_name = font_role = ImageFont.load_default()
                
            draw.text((120, 95), name, fill=(255, 255, 255), font=font_name, anchor="mm")
            draw.text((120, 135), role, fill=color, font=font_role, anchor="mm")
            img.save(path, "PNG")
            print(f"Generated default character avatar: {path}")

# -------------------------------------------------------------
# 2. Stock Footage Retriever (Pixabay)
# -------------------------------------------------------------
def fetch_pixabay_video(query, output_filename):
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        print("PIXABAY_API_KEY missing.")
        return False

    url = "https://pixabay.com/api/videos/"
    params = {"key": api_key, "q": query, "video_type": "all", "per_page": 10, "safesearch": "true"}
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
                        v_res = requests.get(target.get("url"), timeout=40)
                        if v_res.status_code == 200:
                            with open(output_filename, "wb") as f:
                                f.write(v_res.content)
                            return True
    except Exception as e:
        print(f"Pixabay fetch notice: {e}")
    return False

# -------------------------------------------------------------
# 3. Multi-Speaker Audio & ASS Subtitle Synthesizer
# -------------------------------------------------------------
def ms_to_ass(ms):
    cs = int((ms % 1000) / 10)
    total_sec = int(ms / 1000)
    s = total_sec % 60
    m = int(total_sec / 60) % 60
    h = int(total_sec / 3600)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

async def render_dialogue_audio(dialogue_list):
    """
    Synthesizes each character's lines with distinct Edge-TTS voices
    and formats karaoke dialogues placed strictly in the dead center of the 1080x1920 video.
    """
    voices = {
        "Maya": "en-US-JennyNeural",
        "Vikram": "en-US-ChristopherNeural"
    }

    # Alignment=5 places the subtitle exactly at the center (x=540, y=960)
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MayaCenter,DejaVu Sans,68,&H0000D7FF,&H0000FFFF,&H00000000,&HA0000000,1,0,0,0,100,100,1,0,3,4,3,5,60,60,0,1
Style: VikramCenter,DejaVu Sans,68,&H00FFFF00,&H0000FFFF,&H00000000,&HA0000000,1,0,0,0,100,100,1,0,3,4,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    line_audio_files = []
    current_time_ms = 0
    speaker_timeline = []

    for idx, item in enumerate(dialogue_list):
        speaker = item.get("speaker", "Maya")
        text = item.get("text", "")
        voice = voices.get(speaker, "en-US-ChristopherNeural")
        
        line_file = f"line_{idx}.mp3"
        line_audio_files.append(line_file)
        
        communicate = edge_tts.Communicate(text, voice, rate="+2%", pitch="-2Hz")
        submaker = edge_tts.SubMaker()
        
        with open(line_file, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)

        # Get audio segment duration
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", line_file]
        dur_res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        line_duration_sec = float(dur_res.stdout.strip())
        line_duration_ms = int(line_duration_sec * 1000)

        start_s = current_time_ms / 1000.0
        end_s = (current_time_ms + line_duration_ms) / 1000.0
        speaker_timeline.append((start_s, end_s, speaker))

        # Assign speaker tag colors (Maya = Amber, Vikram = Cyan)
        style_name = "MayaCenter" if speaker == "Maya" else "VikramCenter"
        speaker_badge_color = "\\c&H00A5F5&" if speaker == "Maya" else "\\c&H00E996&"
        
        blocks = re.split(r'\n\s*\n', submaker.get_srt().strip())
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
                    if w_end - w_start < 250:
                        w_end = w_start + 250

                    # Displays: [SPEAKER TAG] on top, with the animated spoken word right below in the center
                    center_dialogue = (
                        f"{{{speaker_badge_color}\\fs42\\b1}[ {speaker} ]\\N}}"
                        f"{{\\r{style_name}\\fs72\\t(0,70,\\fscx112\\fscy112)\\t(70,140,\\fscx100\\fscy100)}}{word}"
                    )
                    
                    events.append(f"Dialogue: 0,{ms_to_ass(w_start)},{ms_to_ass(w_end)},{style_name},,0,0,0,,{center_dialogue}")

        current_time_ms += line_duration_ms

    # Combine dialogue audio segments into master track
    with open("audio_concat.txt", "w") as f:
        for a in line_audio_files:
            f.write(f"file '{a}'\n")
            
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio_concat.txt", "-c", "copy", "dialogue_master.mp3"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    with open("subtitles.ass", "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return current_time_ms / 1000.0, speaker_timeline




# -------------------------------------------------------------
# 4. Cinematic Short Assembly with Character HUD Overlays
# -------------------------------------------------------------
def assemble_character_short(video_clips, total_duration, speaker_timeline, output_video="scam_short.mp4"):
    ensure_character_avatars()
    clip_dur = total_duration / len(video_clips)

    # Prepare background video clips (1080x1920)
    prepared_clips = []
    for idx, raw_clip in enumerate(video_clips):
        processed_clip = f"prep_{idx}.mp4"
        prepared_clips.append(processed_clip)
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "3", "-i", raw_clip,
            "-t", f"{clip_dur:.2f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
                   "eq=contrast=1.15:saturation=1.2:brightness=-0.04,vignette=PI/4.2,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", processed_clip
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open("clips.txt", "w") as f:
        for c in prepared_clips:
            f.write(f"file '{c}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "clips.txt", "-c", "copy", "base_video.mp4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Overlay Avatars: Maya on bottom-left (x=60, y=1480), Vikram on bottom-right (x=780, y=1480)
    # Both characters stay visibly on screen throughout the dialogue
    avatar_filter = (
        "[0:v][1:v]overlay=60:1480[v1];"
        "[v1][2:v]overlay=780:1480[v2];"
        "[v2]ass=subtitles.ass[vfinal]"
    )

    ambient_path = "assets/ambient.mp3" if os.path.exists("assets/ambient.mp3") else "ambient.mp3"
    has_ambient = os.path.exists(ambient_path)

    if has_ambient:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "base_video.mp4",
            "-i", "assets/maya.png",
            "-i", "assets/vikram.png",
            "-i", "dialogue_master.mp3",
            "-stream_loop", "-1", "-i", ambient_path,
            "-filter_complex",
            f"{avatar_filter};[4:a]volume=0.10[bg];[3:a][bg]amix=inputs=2:duration=first[afinal]",
            "-map", "[vfinal]", "-map", "[afinal]",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]
    else:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "base_video.mp4",
            "-i", "assets/maya.png",
            "-i", "assets/vikram.png",
            "-i", "dialogue_master.mp3",
            "-filter_complex", avatar_filter,
            "-map", "[vfinal]", "-map", "3:a",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]

    subprocess.run(cmd_final, check=True)
    print("Multi-character Short assembled with visible avatars and alternating voices!")

# -------------------------------------------------------------
# 5. YouTube Upload Handler
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
                    f"#CyberSecurity #ScamAlert #Investigation #TrueCrime #Shorts"
                ),
                "tags": ["CyberSecurity", "ScamAlert", "Investigation", "TrueCrime", "Shorts"],
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
        print("SUCCESS: Published Character Short! Video ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload notice (non-fatal): {e}")

# -------------------------------------------------------------
# 6. Pipeline Orchestrator
# -------------------------------------------------------------
def process_youtube_short(day_entry, story):
    if not story or "dialogue" not in story:
        print("Invalid dialogue story structure passed.")
        return

    queries = story.get("video_queries", ["smartphone call dark", "hacker coding screen", "stressed person phone", "police lights night"])
    video_clips = []
    
    print("Step 1: Downloading dynamic background stock footage...")
    for idx, q in enumerate(queries):
        clip = f"clip_{idx}.mp4"
        if fetch_pixabay_video(q, clip):
            video_clips.append(clip)

    fallbacks = ["hacker dark room", "cyber technology code", "network server", "phone anxiety"]
    fb_idx = 0
    while len(video_clips) < 4 and fb_idx < len(fallbacks):
        clip = f"fb_clip_{fb_idx}.mp4"
        if fetch_pixabay_video(fallbacks[fb_idx], clip):
            video_clips.append(clip)
        fb_idx += 1

    if not video_clips:
        print("No stock footage available. Skipping video build.")
        return

    print("Step 2: Synthesizing multi-character dialogue voices and subtitles...")
    total_dur, timeline = asyncio.run(render_dialogue_audio(story["dialogue"]))

    print("Step 3: Overlaying character badges, kinetic subtitles, and ambient track...")
    assemble_character_short(video_clips, total_dur, timeline)

    full_transcript = " ".join([f"{item['speaker']}: {item['text']}" for item in story["dialogue"]])
    print("Step 4: Uploading to YouTube...")
    upload_to_youtube("scam_short.mp4", story.get("title", "Cyber Threat Investigation"), full_transcript)
