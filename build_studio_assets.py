import os
from PIL import Image, ImageDraw, ImageFont

def make_studio_portrait(name, role, accent_color, output_path):
    # 440x500 high-res studio tile
    img = Image.new("RGBA", (440, 500), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark studio monitor glass background
    draw.rounded_rectangle([(0, 0), (440, 500)], radius=24, fill=(15, 23, 42, 240), outline=(51, 65, 85), width=3)

    # Studio background gradient / glow grid
    for y in range(30, 360, 25):
        draw.line([(20, y), (420, y)], fill=(30, 41, 59, 120), width=1)
    for x in range(30, 420, 35):
        draw.line([(x, 30), (x, 360)], fill=(30, 41, 59, 120), width=1)

    # Realistic Silhouette / Studio Bust Base
    skin = (230, 190, 160) if name == "VIKRAM" else (235, 200, 175)
    suit = (10, 15, 30)

    # Shoulders & Suit
    draw.polygon([(60, 420), (130, 310), (310, 310), (380, 420)], fill=suit)
    draw.line([(130, 310), (220, 420)], fill=accent_color, width=4)
    draw.line([(310, 310), (220, 420)], fill=accent_color, width=4)

    # Neck & Head
    draw.rectangle([(195, 260), (245, 320)], fill=(190, 150, 120))
    draw.polygon([(145, 120), (295, 120), (285, 210), (220, 280), (155, 210)], fill=skin)

    # Hair Styling
    if name == "VIKRAM":
        # Sharp side-swept hair
        draw.polygon([(135, 130), (150, 60), (200, 40), (250, 40), (300, 70), (290, 130), (240, 95), (170, 100)], fill=(25, 28, 36))
        # Tech frames
        draw.rounded_rectangle([(160, 150), (210, 185)], radius=4, outline=accent_color, width=3)
        draw.rounded_rectangle([(230, 150), (280, 185)], radius=4, outline=accent_color, width=3)
        draw.line([(210, 165), (230, 165)], fill=accent_color, width=3)
    else:
        # Long sleek hair
        draw.polygon([(130, 120), (115, 330), (160, 330), (150, 200)], fill=(50, 30, 20))
        draw.polygon([(310, 120), (325, 330), (280, 330), (290, 200)], fill=(50, 30, 20))
        draw.polygon([(130, 130), (150, 55), (220, 40), (285, 55), (310, 130), (260, 95), (180, 95)], fill=(50, 30, 20))
        # Studio on-ear headset
        draw.ellipse([(128, 170), (144, 200)], fill=(245, 158, 11), outline=(255, 255, 255), width=2)
        draw.arc([(135, 185), (210, 230)], start=60, end=140, fill=(245, 158, 11), width=3)
        draw.ellipse([(195, 222), (205, 232)], fill=(239, 68, 68))

    # Eyes & Focus
    draw.ellipse([(175, 160), (195, 175)], fill=(30, 41, 59))
    draw.ellipse([(245, 160), (265, 175)], fill=(30, 41, 59))
    draw.ellipse([(182, 164), (188, 170)], fill=(255, 255, 255))
    draw.ellipse([(252, 164), (258, 170)], fill=(255, 255, 255))

    # Anchor Desk Badge Footer
    draw.rounded_rectangle([(15, 420), (425, 485)], radius=12, fill=(15, 23, 42), outline=accent_color, width=2)
    try:
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except Exception:
        font_name = font_sub = ImageFont.load_default()

    draw.text((220, 442), name, fill=(255, 255, 255), font=font_name, anchor="mm")
    draw.text((220, 468), role, fill=accent_color, font=font_sub, anchor="mm")

    img.save(output_path, "PNG")
    print(f"Studio asset ready: {output_path}")

if __name__ == "__main__":
    os.makedirs("assets", exist_ok=True)
    make_studio_portrait("MAYA", "CRIME DESK // INVESTIGATOR", (245, 158, 11), "assets/maya_studio.png")
    make_studio_portrait("VIKRAM", "THREAT INTEL // ANALYST", (14, 165, 233), "assets/vikram_studio.png")
