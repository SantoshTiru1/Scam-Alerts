import os
import asyncio
import edge_tts
from moviepy.editor import AudioFileClip, ColorClip, TextClip, CompositeVideoClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. Generate Voiceover using Free Microsoft Edge TTS
async def generate_voiceover(text, output_file="scam_audio.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

# 2. Render Vertical 9:16 Video
def make_short_video(headline, summary, audio_path="scam_audio.mp3", output_path="scam_short.mp4"):
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    # 1080x1920 vertical canvas
    bg = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)

    # Title & Text overlays
    badge = TextClip("🚨 DAILY SCAM ALERT", fontsize=44, color="yellow", font="DejaVu-Sans-Bold").set_position(('center', 250)).set_duration(duration)
    title = TextClip(headline, fontsize=42, color="cyan", size=(900, None), method="caption").set_position(('center', 380)).set_duration(duration)
    body = TextClip(summary, fontsize=36, color="white", size=(900, None), method="caption").set_position(('center', 750)).set_duration(duration)
    cta = TextClip("Stay Safe • Details in Description", fontsize=32, color="gray").set_position(('center', 1650)).set_duration(duration)

    video = CompositeVideoClip([bg, badge, title, body, cta]).set_audio(audio)
    video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")

# 3. Upload to YouTube via Official API
def upload_to_youtube(video_path, headline, summary):
    creds = Credentials(
        None,
        refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YOUTUBE_CLIENT_ID"),
        client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": f"⚠️ Scam Alert: {headline[:65]} #Shorts",
            "description": (
                f"{summary}\n\n"
                f"🛡️ Read all daily regional scam reports:\n"
                f"https://santoshtiru1.github.io/Scam-Alerts/\n\n"
                f"#CyberSecurity #ScamAlert #Phishing #Shorts #TechSafety"
            ),
            "tags": ["CyberSecurity", "ScamAlert", "Phishing", "Fraud", "Shorts"],
            "categoryId": "28"  # Science & Technology
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print("Video published! YouTube ID:", response.get("id"))

def process_youtube_short(day_entry):
    # Pick the top India or North America report as today's Short topic
    regions = day_entry.get("regions", {})
    target = regions.get("India") or regions.get("North America") or next(iter(regions.values()))
    
    headline = target.get("headline", "Critical Scam Warning")
    summary = target.get("summary", "")

    # Voice narration script
    narration = f"Cyber scam warning. {headline}. {summary} Share this to keep your friends and family safe."

    asyncio.run(generate_voiceover(narration))
    make_short_video(headline, summary)
    upload_to_youtube("scam_short.mp4", headline, summary)
