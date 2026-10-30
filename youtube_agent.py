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

                        cmd = [
                            "ffmpeg", "-y", "-i", raw_temp,
                            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                            path
                        ]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                        if os.path.exists(raw_temp):
                            os.remove(raw_temp)
                        print(f"Ready: {path}")
            except Exception as e:
                print(f"Notice downloading {path}: {e}")

# -------------------------------------------------------------
# 2. Audio & Clean 3-Word Chunk Subtitles
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
                    w_start = current_time_ms + (g[0] * 3600000 + g[1] * 60000 + g[2] * 1000 + g[3])
                    w_end = current_time_ms + (g[4] * 3600000 + g[5] * 60000 + g[6] * 1000 + g[7])
                    words_data.append((w_start, w_end, word))

        if words_data:
            chunk_size = 3
            for i in range(0, len(words_data), chunk_size):
                chunk = words_data[i:i + chunk_size]
                c_start = chunk[0][0]
                c_end = max(chunk[-1][1], c_start + 400)
                phrase = " ".join([w[2] for w in chunk]).upper()

                speaker_tag = f"[{speaker.upper()}]"
                srt_entries.append(
                    f"{srt_counter}\n"
                    f"{ms_to_srt_time(c_start)} --> {ms_to_srt_time(c_end)}\n"
                    f"<font color=\"{tag_color}\"><b>{speaker_tag}</b></font>\n{phrase}\n"
                )
                srt_counter += 1
        else:
            words = text.split()
            chunk_size = 4
            num_chunks = max(1, len(words) // chunk_size)
            chunk_dur = line_duration_ms // num_chunks
            for i in range(0, len(words), chunk_size):
                sub_words = " ".join(words[i:i + chunk_size]).upper()
                w_start = current_time_ms + (i // chunk_size) * chunk_dur
                w_end = min(current_time_ms + line_duration_ms, w_start + chunk_dur)
                speaker_tag = f"[{speaker.upper()}]"
                srt_entries.append(
                    f"{srt_counter}\n"
                    f"{ms_to_srt_time(w_start)} --> {ms_to_srt_time(w_end)}\n"
                    f"<font color=\"{tag_color}\"><b>{speaker_tag}</b></font>\n{sub_words}\n"
                )
                srt_counter += 1

        current_time_ms += line_duration_ms

    with open("audio_concat.txt", "w") as f:
        for a in line_audio_files:
            f.write(f"file '{a}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio_concat.txt", "-c", "copy", "dialogue_master.mp3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    srt_path = os.path.abspath("subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries) + "\n")
        f.flush()
        os.fsync(f.fileno())

    return current_time_ms / 1000.0, line_segments

# -------------------------------------------------------------
# 3. Assemble Human Presenter Cuts (Locked Exactly in the Middle)
# -------------------------------------------------------------
def assemble_human_presenter_short(line_segments, output_video="scam_short.mp4"):
    ensure_presenter_clips()

    cut_clips = []
    for idx, (audio_file, duration, speaker) in enumerate(line_segments):
        cut_clip = f"cut_{idx}.mp4"
        cut_clips.append(cut_clip)

        source_video = "assets/maya_presenter.mp4" if speaker == "Maya" else "assets/vikram_presenter.mp4"

        cmd = [
            "ffmpeg", "-y", "-stream_loop", "5", "-i", source_video,
            "-t", f"{duration:.2f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
                   "eq=contrast=1.08:saturation=1.12:brightness=-0.02,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
            cut_clip
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open("cuts.txt", "w") as f:
        for c in cut_clips:
            f.write(f"file '{c}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "cuts.txt", "-c", "copy", "base_presenters.mp4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Alignment=10 (Middle-Center of the 1080x1920 frame)
    # MarginV=0 (Dead center on y=960)
    # MarginL=60, MarginR=60 (Safe horizontal padding so text never clips on mobile)
    sub_filter = (
        "subtitles=filename=subtitles.srt:force_style='"
        "Fontname=DejaVu Sans,Fontsize=50,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H90000000,"
        "BorderStyle=3,Outline=4,Shadow=0,Alignment=10,MarginL=60,MarginR=60,MarginV=0'"
    )

    ambient_path = "assets/ambient.mp3"
    has_ambient = os.path.exists(ambient_path)

    if has_ambient:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "base_presenters.mp4",
            "-i", "dialogue_master.mp3",
            "-stream_loop", "-1", "-i", ambient_path,
            "-filter_complex",
            f"[0:v]{sub_filter}[vfinal];[2:a]volume=0.10[bg];[1:a][bg]amix=inputs=2:duration=first[afinal]",
            "-map", "[vfinal]", "-map", "[afinal]",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]
    else:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "base_presenters.mp4",
            "-i", "dialogue_master.mp3",
            "-vf", sub_filter,
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]

    subprocess.run(cmd_final, check=True)
    print("Human Presenter Short assembled successfully with centered subtitles!")

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
        print("SUCCESS: Published Human Presenter Short! Video ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload notice (non-fatal): {e}")

# -------------------------------------------------------------
# 5. Pipeline Orchestrator
# -------------------------------------------------------------
def process_youtube_short(day_entry, story):
    if not story or "dialogue" not in story:
        print("Invalid dialogue story structure passed.")
        return

    print("Step 1: Synthesizing character dialogue & chunked subtitles...")
    total_dur, line_segments = asyncio.run(render_dialogue_audio(story["dialogue"]))

    print("Step 2: Cutting between human presenters (Maya & Vikram)...")
    assemble_human_presenter_short(line_segments)

    full_transcript = " ".join([f"{item['speaker']}: {item['text']}" for item in story["dialogue"]])
    print("Step 3: Uploading to YouTube...")
    upload_to_youtube("scam_short.mp4", story.get("title", "Cyber Threat Investigation"), full_transcript)
