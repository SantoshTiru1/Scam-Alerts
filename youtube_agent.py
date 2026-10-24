import os
import re
import urllib.parse
import asyncio
import subprocess
import requests
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -------------------------------------------------------------
# 1. Download AI Imagery (100% Free, No API Key via Pollinations)
# -------------------------------------------------------------
def fetch_ai_image(prompt, filename, width=1080, height=1920):
    """Fetches high-quality cinematic 9:16 vertical images."""
    clean_prompt = urllib.parse.quote(f"{prompt}, 9:16 vertical aspect ratio, dark cinematic documentary style, film grain, hyperrealistic, dramatic volumetric lighting")
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width={width}&height={height}&nologo=true&seed={hash(prompt) % 10000}"
    try:
        res = requests.get(url, timeout=35)
        if res.status_code == 200:
            with open(filename, "wb") as f:
                f.write(res.content)
            print(f"Downloaded scene image: {filename}")
            return True
    except Exception as e:
        print(f"Image fetch error: {e}")
    return False

# -------------------------------------------------------------
# 2. Voiceover + Subtitle Generation
# -------------------------------------------------------------
async def generate_narration_with_subtitles(text, audio_out="scam_audio.mp3", srt_out="captions.vtt"):
    """Generates Edge-TTS speech and aligned subtitle timestamps."""
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="-2%", pitch="-2Hz")
    submaker = edge_tts.SubMaker()
    
    with open(audio_out, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
                
    with open(srt_out, "w", encoding="utf-8") as file:
        file.write(submaker.get_srt())
    print("Audio & word subtitles generated.")

def get_duration(media_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", media_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 55.0

# -------------------------------------------------------------
# 3. Cinematic Video Assembly (Ken Burns Zoom + Burned Captions)
# -------------------------------------------------------------
def assemble_cinematic_short(image_files, audio_file="scam_audio.mp3", srt_file="captions.vtt", output_video="scam_short.mp4"):
    total_duration = get_duration(audio_file)
    num_images = len(image_files)
    clip_duration = total_duration / max(num_images, 1)

    # Step A: Convert each image to a zooming 1080x1920 clip (Ken Burns effect)
    clip_names = []
    for i, img_path in enumerate(image_files):
        clip_name = f"clip_{i}.mp4"
        clip_names.append(clip_name)
        # Ken Burns zoom-in filter: zooms from 1.0 to 1.15 smoothly
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-t", f"{clip_duration:.2f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                   "zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125:s=1080x1920:fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            clip_name
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step B: Concat visual clips together
    with open("clips.txt", "w") as f:
        for c in clip_names:
            f.write(f"file '{c}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", "clips.txt",
        "-c", "copy", "visual_track.mp4"
    ]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step C: Mix Audio (Narration + Ambient BGM) and Burn Styled Center Subtitles
    has_ambient = os.path.exists("assets/ambient.mp3")
    
    # Subtitle styling: bold yellow-white font, centered, uppercase, black stroke
    subtitle_filter = (
        f"subtitles={srt_file}:force_style='Alignment=10,FontSize=22,FontName=DejaVu Sans,"
        f"Bold=1,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2'"
    )

    if has_ambient:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "visual_track.mp4",
            "-i", audio_file,
            "-i", "assets/ambient.mp3",
            "-filter_complex",
            f"[0:v]{subtitle_filter}[v];[2:a]volume=0.12[bg];[1:a][bg]amix=inputs=2:duration=first[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]
    else:
        cmd_final = [
            "ffmpeg", "-y",
            "-i", "visual_track.mp4",
            "-i", audio_file,
            "-vf", subtitle_filter,
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_video
        ]

    subprocess.run(cmd_final, check=True)
    print("Cinematic Short assembled with Ken Burns & bold captions!")

# -------------------------------------------------------------
# 4. YouTube Upload Handler
# -------------------------------------------------------------
def upload_to_youtube(video_path, title, script):
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube tokens missing. Skipping upload.")
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
                "description": f"{script}\n\n🛡️ Real-time cyber threats & prevention portal:\nhttps://santoshtiru1.github.io/Scam-Alerts/\n\n#CyberSecurity #ScamAlert #TrueCrime #Shorts",
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
        print("SUCCESS: Published Documentary Short! ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload non-fatal notice: {e}")

# -------------------------------------------------------------
# 5. Pipeline Orchestrator
# -------------------------------------------------------------
def process_youtube_short(day_entry, story=None):
    if not story:
        story = {
            "title": "Digital Arrest Syndicate Exposed",
            "voiceover": "Millions of dollars were drained this week by organized digital arrest syndicates. Victims receive an urgent video call from fraudsters wearing forged police uniforms, brandishing fake warrants. Under intense psychological intimidation, victims are coerced into transferring their life savings to so-called verification accounts. Remember: real police and judicial courts will never arrest you over a video call or demand bank transfers to clear your name. Stay safe and share this warning.",
            "image_prompts": [
                "dark room, person on video call looking terrified, police uniform visible on screen, moody lighting",
                "close up of fake legal document with arrest warrant stamp, dramatic shadows, cinematic",
                "wire transfer confirmed screen on smartphone, empty savings account, devastating mood",
                "modern digital cybercrime defense lock, glowing blue holographic shield, 8k"
            ]
        }

    prompts = story.get("image_prompts", [])
    downloaded_images = []
    
    print("Generating scene imagery...")
    for idx, prompt in enumerate(prompts):
        img_file = f"scene_{idx}.jpg"
        if fetch_ai_image(prompt, img_file):
            downloaded_images.append(img_file)

    if not downloaded_images:
        print("Fallback image generation...")
        fetch_ai_image("cyber crime warning digital screen", "scene_0.jpg")
        downloaded_images = ["scene_0.jpg"]

    print("Synthesizing voiceover and subtitles...")
    asyncio.run(generate_narration_with_subtitles(story.get("voiceover", "")))

    print("Rendering Ken Burns video and burning captions...")
    assemble_cinematic_short(downloaded_images)

    print("Uploading to YouTube...")
    upload_to_youtube("scam_short.mp4", story.get("title", "Cyber Scam Warning"), story.get("voiceover", ""))
