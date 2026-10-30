import os
import random
import requests
import subprocess

API_KEY = os.getenv("PIXABAY_API_KEY")

def fetch_presenter_video_url(query):
    if not API_KEY:
        raise ValueError("PIXABAY_API_KEY environment variable is not set.")

    url = "https://pixabay.com/api/videos/"
    params = {
        "key": API_KEY,
        "q": query,
        "video_type": "all",
        "per_page": 10,
        "safesearch": "true"
    }

    res = requests.get(url, params=params, timeout=20)
    res.raise_for_status()
    data = res.json()
    hits = data.get("hits", [])
    
    if not hits:
        raise RuntimeError(f"No Pixabay videos found for query: '{query}'")

    # Pick the best available video quality
    hit = hits[0]
    vids = hit.get("videos", {})
    target = vids.get("large") or vids.get("medium") or vids.get("small")
    
    if target and target.get("url"):
        return target["url"]
    
    raise RuntimeError(f"No valid MP4 download stream found for: '{query}'")

def download_and_format(url, output_path):
    print(f"Downloading stream for {output_path}...")
    temp_raw = f"raw_{os.path.basename(output_path)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(temp_raw, "wb") as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)

    print(f"Converting {temp_raw} into 1080x1920 vertical format -> {output_path}...")
    cmd = [
        "ffmpeg", "-y", "-i", temp_raw,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        output_path
    ]
    subprocess.run(cmd, check=True)

    if os.path.exists(temp_raw):
        os.remove(temp_raw)
    print(f"✓ Saved: {output_path}")

def main():
    os.makedirs("assets", exist_ok=True)

    # 1. Maya Presenter (Female News/Podcast Presenter speaking to camera)
    maya_target = "assets/maya_presenter.mp4"
    if not os.path.exists(maya_target):
        try:
            maya_url = fetch_presenter_video_url("woman presenter talking to camera")
            download_and_format(maya_url, maya_target)
        except Exception as e:
            print(f"Failed to fetch Maya presenter: {e}")

    # 2. Vikram Presenter (Male Analyst/Tech Presenter speaking to camera)
    vikram_target = "assets/vikram_presenter.mp4"
    if not os.path.exists(vikram_target):
        try:
            vikram_url = fetch_presenter_video_url("man talking to camera interview")
            download_and_format(vikram_url, vikram_target)
        except Exception as e:
            print(f"Failed to fetch Vikram presenter: {e}")

if __name__ == "__main__":
    main()
