import os
import re
import json
import asyncio
import subprocess
import urllib.parse
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -------------------------------------------------------------
# 1. Generate Ink Explainer Scene Illustrations (With Fallback)
# -------------------------------------------------------------
def create_fallback_sketch(scene_idx, category, output_filename):
    """Guaranteed instant procedural ink-explainer canvas if external API drops."""
    img = Image.new("RGBA", (1080, 1920), (250, 250, 250, 255))
    d = ImageDraw.Draw(img)

    # Subtle grid paper background
    for y in range(0, 1920, 40):
        d.line([(0, y), (1080, y)], fill=(235, 235, 235), width=1)
    for x in range(0, 1080, 40):
        d.line([(x, 0), (x, 1920)], fill=(235, 235, 235), width=1)

    # Clean ink border
    d.rounded_rectangle([(40, 60), (1040, 1860)], radius=30, outline=(25, 25, 25), width=8)

    # Bold category badge at top
    d.rounded_rectangle([(140, 140), (940, 240)], radius=20, fill=(25, 25, 25))
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except Exception:
        font_large = font_sub = ImageFont.load_default()

    d.text((540, 190), f"CYBER THREAT INTEL", fill=(255, 215, 0), font=font_large, anchor="mm")

    # Expressive hand-drawn style Stickman
    # Head
    d.ellipse([(440, 500), (640, 700)], fill=(255, 255, 255), outline=(25, 25, 25), width=10)
    # Eyes & Mouth based on scene
    if scene_idx in [0, 2]: # Shocked
        d.ellipse([(490, 560), (520, 600)], fill=(25, 25, 25))
        d.ellipse([(560, 560), (590, 600)], fill=(25, 25, 25))
        d.ellipse([(515, 630), (565, 680)], fill=(25, 25, 25))
    else: # Investigator / Alert
        d.rectangle([(470, 560), (530, 595)], fill=(14, 165, 233), outline=(25, 25, 25), width=6)
        d.rectangle([(550, 560), (610, 595)], fill=(14, 165, 233), outline=(25, 25, 25), width=6)
        d.line([(530, 578), (550, 578)], fill=(25, 25, 25), width=6)
        d.arc([(490, 620), (590, 670)], start=10, end=170, fill=(25, 25, 25), width=8)

    # Torso
    d.line([(540, 700), (540, 1100)], fill=(25, 25, 25), width=12)

    # Arms & Legs
    d.line([(540, 800), (400, 950)], fill=(25, 25, 25), width=10)
    d.line([(540, 800), (680, 950)], fill=(25, 25, 25), width=10)
    d.line([(540, 1100), (430, 1350)], fill=(25, 25, 25), width=12)
    d.line([(540, 1100), (650, 1350)], fill=(25, 25, 25), width=12)

    # Target scam badge
    d.rounded_rectangle([(140, 1450), (940, 1650)], radius=20, fill=(245, 245, 245), outline=(25, 25, 25), width=6)
    d.text((540, 1550), category[:36].upper(), fill=(25, 25, 25), font=font_sub, anchor="mm")

    img.save(output_filename, "PNG")

def fetch_ink_explainer_frame(scene_idx, category, scene_desc, output_filename):
    clean_desc = re.sub(r'[^a-zA-Z0-9 ]', '', scene_desc)
    prompt = (
        f"minimalist stickman line drawing, ink explainer aesthetic, black ink on clean white background, "
        f"expressive stick figure character, comic illustration, simple doodle, {clean_desc}, sharp lines"
    )
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&nologo=true&seed={os.urandom(2).hex()}"

    try:
        res = requests.get(url, timeout=20)
        if res.status_code == 200 and len(res.content) > 10000:
            with open(output_filename, "wb") as f:
                f.write(res.content)
            return True
    except Exception as e:
        print(f"API notice on scene {scene_idx}: {e}")

    # Seamless instant fallback
    create_fallback_sketch(scene_idx, category, output_filename)
    return True

# -------------------------------------------------------------
# 2. Audio & Centered Compact Subtitles (20% Middle Area)
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

    # Ink Explainer Subtitle Style: Dark rounded pill box, high contrast, middle-center (Alignment=5)
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: InkSub,DejaVu Sans,34,&H00FFFFFF,&H0000FFFF,&H00000000,&HB0000000,1,0,0,0,100,100,1,0,3,3,1,5,160,160,0,1

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

        tag_color = "\\c&H00D7FF&" if speaker == "Maya" else "\\c&H00E996&"

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
                entry = f"{{{tag_color}\\fs24\\b1}}[{speaker.upper()}]\\N{{\\rInkSub\\fs34\\b1}}{phrase}"
                events.append(f"Dialogue: 0,{ms_to_ass(c_start)},{ms_to_ass(c_end)},InkSub,,0,0,0,,{entry}")
        else:
            words = text.upper().split()
            chunk_size = 3
            num_chunks = max(1, len(words) // chunk_size)
            chunk_dur = line_duration_ms // num_chunks
            for i in range(0, len(words), chunk_size):
                sub_words = " ".join(words[i:i + chunk_size])
                w_start = current_time_ms + (i // chunk_size) * chunk_dur
                w_end = min(current_time_ms + line_duration_ms, w_start + chunk_dur)
                entry = f"{{{tag_color}\\fs24\\b1}}[{speaker.upper()}]\\N{{\\rInkSub\\fs34\\b1}}{sub_words}"
                events.append(f"Dialogue: 0,{ms_to_ass(w_start)},{ms_to_ass(w_end)},InkSub,,0,0,0,,{entry}")

        current_time_ms += line_duration_ms

    with open("audio_concat.txt", "w") as f:
        for a in line_audio_files:
            f.write(f"file '{a}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio_concat.txt", "-c", "copy", "dialogue_master.mp3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open("subtitles.ass", "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return current_time_ms / 1000.0, line_durations

# -------------------------------------------------------------
# 3. Animate Sketch Frames with Dynamic Motion & Subtitles
# -------------------------------------------------------------
def assemble_ink_explainer_video(image_files, line_durations, output_video="scam_short.mp4"):
    clip_files = []
    total_duration = sum(dur for dur, _ in line_durations)
    dur_per_scene = total_duration / len(image_files)

    for idx, img_path in enumerate(image_files):
        clip_name = f"scene_{idx}.mp4"
        clip_files.append(clip_name)

        zoom_expr = "zoom+0.0012" if idx % 2 == 0 else "zoom-0.0010"
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img_path,
            "-t", f"{dur_per_scene:.2f}",
            "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                   f"zoompan=z='min(max({zoom_expr},1.0),1.15)':d={int(dur_per_scene*30)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                   f"format=yuv420p",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
            clip_name
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open("scenes_list.txt", "w") as f:
        for c in clip_files:
            f.write(f"file '{c}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "scenes_list.txt", "-c", "copy", "raw_montage.mp4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    cmd_final = [
        "ffmpeg", "-y",
        "-i", "raw_montage.mp4",
        "-i", "dialogue_master.mp3",
        "-vf", "ass=subtitles.ass",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-shortest", output_video
    ]
    subprocess.run(cmd_final, check=True)
    print("Ink Explainer Short assembled successfully!")

# -------------------------------------------------------------
# 4. YouTube Upload Handler
# -------------------------------------------------------------
def upload_to_youtube(video_path, title, description):
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube credentials missing in Secrets. Skipping upload.")
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
                    f"🛡️ Daily Cyber Intelligence Protocols:\n"
                    f"https://santoshtiru1.github.io/Scam-Alerts/\n\n"
                    f"#Animation #Stickman #Investigation #CyberSecurity #Shorts"
                ),
                "tags": ["Animation", "Stickman", "CyberSecurity", "Investigation", "Shorts"],
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
        print("SUCCESS: Published Ink Explainer Short! Video ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload notice: {e}")

# -------------------------------------------------------------
# 5. Pipeline Orchestrator
# -------------------------------------------------------------
def process_youtube_short(day_entry, story):
    if not story or "dialogue" not in story:
        print("Invalid dialogue story structure passed.")
        return

    category = story.get("category", "Cyber Scam")
    print(f"\n--- Generating Visuals for Category: {category} ---")

    scene_descriptions = [
        f"stickman looking shocked at smartphone with {category} trap on screen",
        f"shady stickman criminal wearing hoodie operating laptop computer with evil code",
        f"stickman crying with empty pockets and wallet showing money flying away",
        f"stickman police investigator pointing finger at warning shield with red stop icon"
    ]

    images = []
    for idx, desc in enumerate(scene_descriptions):
        img_file = f"sketch_{idx}.png"
        if fetch_ink_explainer_frame(idx, category, desc, img_file):
            images.append(img_file)

    if not images:
        print("No artwork available. Skipping video build.")
        return

    print("Synthesizing dialogue audio and centered subtitles...")
    total_dur, line_durations = asyncio.run(render_dialogue_audio(story["dialogue"]))

    print("Compositing Ink Explainer animation...")
    assemble_ink_explainer_video(images, line_durations)

    full_transcript = " ".join([f"{item['speaker']}: {item['text']}" for item in story["dialogue"]])
    print("Uploading to YouTube...")
    upload_to_youtube("scam_short.mp4", story.get("title", f"The {category} Trap"), full_transcript)
