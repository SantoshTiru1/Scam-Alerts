import os
import asyncio
import subprocess
import textwrap
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

async def generate_voiceover(text, output_file="scam_audio.mp3"):
    """Generates a steady, deep documentary narration voiceover."""
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="-2%", pitch="-3Hz")
    await communicate.save(output_file)

def get_audio_duration(audio_path="scam_audio.mp3"):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 50.0

def draw_story_card(tag, main_text, sub_text, rule_text, output_path, accent_color=(239, 68, 68)):
    """Renders a 1080x1920 high-contrast cinematic typography card."""
    width, height = 1080, 1920
    img = Image.new("RGB", (width, height), color=(10, 15, 26))
    draw = ImageDraw.Draw(img)

    # Ambient border glow
    draw.rectangle([(0, 0), (width, 28)], fill=accent_color)
    draw.rounded_rectangle([(50, 100), (1030, 1820)], radius=32, outline=(30, 41, 59), width=3)

    try:
        font_tag = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 62)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        font_rule = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    except Exception:
        font_tag = font_main = font_sub = font_rule = ImageFont.load_default()

    # Chapter Tag
    draw.rounded_rectangle([(90, 150), (450, 220)], radius=12, fill=accent_color)
    draw.text((115, 166), tag, fill=(255, 255, 255), font=font_tag)

    # Main Dramatic Text
    wrapped_main = textwrap.fill(main_text, width=24)
    draw.text((90, 320), wrapped_main, fill=(255, 255, 255), font=font_main, spacing=18)

    # Narrative Breakdown
    draw.line([(90, 720), (990, 720)], fill=(51, 65, 85), width=2)
    wrapped_sub = textwrap.fill(sub_text, width=32)
    draw.text((90, 780), wrapped_sub, fill=(203, 213, 225), font=font_sub, spacing=20)

    # Bottom Defense Card
    if rule_text:
        draw.rounded_rectangle([(90, 1480), (990, 1720)], radius=24, fill=(19, 27, 46), outline=(56, 189, 248), width=3)
        draw.text((130, 1520), "🛡️ THE SURVIVAL RULE:", fill=(56, 189, 248), font=font_tag)
        wrapped_rule = textwrap.fill(rule_text, width=34)
        draw.text((130, 1580), wrapped_rule, fill=(248, 250, 252), font=font_rule, spacing=14)

    img.save(output_path)

def render_cinematic_short(story, audio_path="scam_audio.mp3", output_video="scam_short.mp4"):
    total_sec = get_audio_duration(audio_path)
    part_sec = total_sec / 3.0

    # Scene 1: The Hook & Opening
    draw_story_card(
        tag="🚨 CRITICAL INCIDENT",
        main_text=story.get("hook", "A New Cyber Trap Unfolds"),
        sub_text=story.get("scene_1", ""),
        rule_text="",
        output_path="scene1.png",
        accent_color=(239, 68, 68) # Red
    )

    # Scene 2: The Trap & Execution
    draw_story_card(
        tag="⚠️ HOW THE TRAP WORKED",
        main_text="The Pressure & Panic",
        sub_text=story.get("scene_2", "") + "\n\n" + story.get("scene_3", ""),
        rule_text="",
        output_path="scene2.png",
        accent_color=(245, 158, 11) # Amber
    )

    # Scene 3: The Fallout & Defense Rule
    draw_story_card(
        tag="🛡️ ESSENTIAL DEFENSE",
        main_text="Don't Be Next",
        sub_text=story.get("scene_3", "Never trust unsolicited urgent communications."),
        rule_text=story.get("defense_rule", "Verify through official portals before sending money."),
        output_path="scene3.png",
        accent_color=(14, 165, 233) # Cyan
    )

    # Concat file for FFmpeg
    with open("scenes.txt", "w") as f:
        f.write(f"file 'scene1.png'\nduration {part_sec:.2f}\n")
        f.write(f"file 'scene2.png'\nduration {part_sec:.2f}\n")
        f.write(f"file 'scene3.png'\nduration {part_sec:.2f}\n")
        f.write("file 'scene3.png'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", "scenes.txt",
        "-i", audio_path,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_video
    ]
    subprocess.run(cmd, check=True)
    print(f"Rendered {total_sec:.1f}s story video successfully.")

def upload_to_youtube(video_path, story):
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube tokens missing in GitHub Secrets. Skipping.")
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

        title = f"⚠️ {story.get('hook')[:70]} #Shorts"
        description = (
            f"{story.get('full_voiceover')}\n\n"
            f"🛡️ Matrix Rule: {story.get('defense_rule')}\n\n"
            f"Explore full daily threat radar & live reporting tools:\n"
            f"https://santoshtiru1.github.io/Scam-Alerts/\n\n"
            f"#ScamAlert #CyberSecurity #TrueCrime #TechSafety #Shorts"
        )

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["CyberSecurity", "ScamAlert", "Phishing", "TrueCrime", "Shorts"],
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
        print("SUCCESS: Published Documentary Short to YouTube! Video ID:", res.get("id"))
    except Exception as e:
        print(f"YouTube Upload Failed (non-fatal): {e}")

def process_youtube_short(day_entry, story=None):
    if not story:
        story = {
            "hook": "Millions Lost to Digital Arrest Scams This Week.",
            "scene_1": "Victims receive a video call from someone claiming to be federal police.",
            "scene_2": "They display forged arrest warrants and order the victim to stay on camera.",
            "scene_3": "Life savings are wired to 'safe RBI clearing accounts' that vanish instantly.",
            "defense_rule": "No law enforcement agency conducts arrests or court hearings over Skype.",
            "full_voiceover": "Millions of dollars were drained this week by organized digital arrest syndicates. Victims receive an urgent video call from fraudsters wearing forged police uniforms, brandishing fake warrants. Under intense psychological intimidation, victims are coerced into transferring their life savings to so-called verification accounts. Remember: real police and judicial courts will never arrest you over a video call or demand bank transfers to clear your name. Stay safe and share this warning."
        }

    print("Step 1: Generating 55s narrative narration...")
    asyncio.run(generate_voiceover(story.get("full_voiceover")))

    print("Step 2 & 3: Rendering multi-scene story video...")
    render_cinematic_short(story)

    print("Step 4: Publishing to YouTube Shorts...")
    upload_to_youtube("scam_short.mp4", story)
