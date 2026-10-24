import os
import json
import re
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from groq import Groq
from youtube_agent import process_youtube_short

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Use the fast, universally available free Groq model
MODEL_NAME = "llama-3.1-8b-instant"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

REGIONS = [
    "North America",
    "South America",
    "Europe",
    "India",
    "Singapore",
    "China",
    "Japan",
    "Rest of the World"
]

def fetch_rss_articles(query):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    articles = []
    try:
        res = requests.get(rss_url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:3]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                description = item.findtext("description", "")
                
                soup = BeautifulSoup(description, "html.parser")
                clean_text = soup.get_text()

                if link and not link.startswith("https://www.google.com/search"):
                    articles.append({
                        "title": title,
                        "body": clean_text if clean_text else title,
                        "url": link
                    })
    except Exception as e:
        print(f"RSS warning for {query}: {e}")
        
    return articles

def fetch_india_official_scams():
    portal_url = "https://cybercrime.gov.in/Webform/daily-digest.aspx"
    base_url = "https://cybercrime.gov.in/Webform/"

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        res = session.get(portal_url, timeout=6, verify=False)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            digest_links = []
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]
                if re.search(r"daily\s*digest", text, re.IGNORECASE) or ("digest" in href.lower() and href.endswith(".pdf")):
                    full_link = href if href.startswith("http") else urllib.parse.urljoin(base_url, href)
                    digest_links.append({
                        "title": text if len(text) > 10 else f"I4C Daily Cyber Digest: {text}",
                        "body": f"Official National Cyber Crime Reporting Portal Daily Digest Advisory ({text}).",
                        "url": full_link
                    })

            if digest_links:
                return digest_links[0]
    except Exception as e:
        print(f"Cybercrime.gov.in timeout/notice: {e}")

    # Fallback to direct CERT-In / India cyber alerts
    fallback_articles = fetch_rss_articles("India cyber crime scam phishing CERT-In")
    if fallback_articles:
        return fallback_articles[0]

    return {
        "title": "National Cyber Crime Reporting Portal Advisory",
        "body": "Active financial fraud campaigns using malicious APK links and digital arrest threats reported.",
        "url": portal_url
    }

def fetch_scam_for_region(region):
    if region == "India":
        return fetch_india_official_scams()

    query_map = {
        "North America": "US cyber security scam phishing fraud news",
        "South America": "Latin America cyber security fraud scam",
        "Europe": "Europe UK cyber crime phishing scam news",
        "Singapore": "Singapore cyber security scam police advisory phishing",
        "China": "China cyber fraud scam phishing news",
        "Japan": "Japan cyber security fraud phishing scam",
        "Rest of the World": "Global cyber fraud scam attack news"
    }

    query = query_map.get(region, f"{region} cyber crime scam")
    articles = fetch_rss_articles(query)
    
    if articles:
        return articles[0]

    return {
        "title": f"Active Cyber Fraud Campaign Target: {region}",
        "body": f"Phishing threats targeting consumers and online credentials reported across {region}.",
        "url": "https://thehackernews.com"
    }

def summarize_scam(region, news_item):
    prompt = f"""
You are a cybersecurity threat analyst.
Region / Country: {region}
Title: {news_item.get('title')}
Details: {news_item.get('body')}

Task:
Write a threat summary strictly under 100 words.
Structure:
- Threat Vector: How the scam works
- Target: Who is targeted
- Prevention: How to stay safe
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a concise cyber intelligence analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=220
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Error for {region}: {e}")
        return news_item.get("body", "Summary currently unavailable.")

def post_to_telegram(day_entry):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Telegram tokens not set. Skipping.")
        return

    date_str = day_entry.get("date", "Today")
    regions_data = day_entry.get("regions", {})

    message = f"🚨 *Global Cyber Scam Alert — {date_str}*\n\n"
    ordered_keys = sorted(regions_data.keys(), key=lambda x: (x != "India", x))

    for region in ordered_keys:
        info = regions_data[region]
        headline = info.get("headline", f"{region} Alert")
        summary = info.get("summary", "").replace("*", "").split("\n")[0]
        source = info.get("source", "")

        message += f"🌍 *{region}*: {headline}\n"
        message += f"_{summary}_\n"
        if source and source != "#":
            message += f"[🔗 Read Primary Report]({source})\n"
        message += "\n"

    message += "🌐 *Full Interactive Digest & Archives:*\n"
    message += "https://santoshtiru1.github.io/Scam-Alerts/\n\n"
    message += "#CyberSecurity #ScamAlert #Phishing #India"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            print("Telegram alert delivered successfully!")
        else:
            print(f"Telegram error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Telegram send error: {e}")

def post_to_whatsapp(day_entry):
    phone = os.getenv("WHATSAPP_PHONE")
    apikey = os.getenv("WHATSAPP_APIKEY")

    if not phone or not apikey:
        print("WhatsApp secrets not configured. Skipping WhatsApp alert.")
        return

    date_str = day_entry.get("date", "Today")
    regions = day_entry.get("regions", {})

    msg = f"🚨 *Global Cyber Scam Digest — {date_str}*\n\n"
    priority_order = ["India", "Singapore", "North America", "Europe"]
    for reg in priority_order:
        if reg in regions:
            headline = regions[reg].get("headline", "")[:75]
            msg += f"• *{reg}*: {headline}\n"

    msg += "\n🌐 *Full Reports & Prevention Tips:*\nhttps://santoshtiru1.github.io/Scam-Alerts/"

    try:
        encoded_msg = urllib.parse.quote(msg)
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={apikey}"
        res = requests.get(url, timeout=15)
        print("WhatsApp CallMeBot status:", res.status_code)
    except Exception as e:
        print("WhatsApp error:", e)

def generate_day_report(target_date):
    print(f"\n--- Gathering reports for {target_date.strftime('%Y-%m-%d')} ---")
    day_entry = {
        "date": target_date.strftime("%Y-%m-%d"),
        "regions": {}
    }
    for region in REGIONS:
        print(f"Analyzing: {region}...")
        item = fetch_scam_for_region(region)
        summary = summarize_scam(region, item)
        day_entry["regions"][region] = {
            "headline": item.get("title"),
            "summary": summary,
            "source": item.get("url")
        }
    return day_entry


def generate_cinematic_story(day_entry):
    """
    Selects the most dangerous/dramatic scam of the day across all 8 regions
    and prompts Groq to script a gripping, true-crime narrative complete
    with context-aware AI visual prompts for every scene.
    """
    regions = day_entry.get("regions", {})
    # Prioritize India or high-impact fraud
    target_region = "India" if "India" in regions else next(iter(regions), "Global")
    scam = regions.get(target_region, {})

    headline = scam.get("headline", "High-Tech Cyber Trap")
    summary = scam.get("summary", "")

    prompt = f"""
You are an investigative documentary director producing a 55-second YouTube Short about this real-world scam:
Region: {target_region}
Headline: {headline}
Details: {summary}

Output strictly valid JSON with no markdown wrapping and these exact keys:
{{
  "title": "Shocking Short Title under 60 chars",
  "voiceover": "A continuous 120-135 word suspenseful narrative script. Start with an arresting hook. Explain the exact trap and psychological manipulation. End with one strict survival rule.",
  "image_prompts": [
    "Cinematic shot, dark mood, tense atmosphere representing the victim receiving the initial call or message, 8k, photorealistic, vertical framing, moody lighting",
    "Cinematic shot, computer screens with digital transfer codes, cyber fraud operation, dark room, red ambient light, dramatic shadows",
    "Cinematic shot, distressed person holding phone in disbelief, bank balance screen blurred, intense emotional lighting",
    "Cinematic shot, official cyber shield badge or law enforcement padlock on digital grid, blue emergency lighting, high resolution"
  ]
}}
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a master true-crime documentary director. Output raw JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=650
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print("Fallback story generation notice:", e)
        return {
            "title": f"The {headline[:40]} Trap",
            "voiceover": f"Millions were lost this week to a ruthless new operation. It begins with an urgent alert regarding {headline[:30]}. Fraudsters impersonate senior officials, isolating victims for hours through psychological fear. They demand instant transfers to verify innocence. By the time victims realize what happened, their life savings have vanished into untraceable mule accounts. Remember: legitimate authorities will never demand money transfers or remote access over a phone call.",
            "image_prompts": [
                "dark cinematic room, glowing smartphone screen displaying alert, moody lighting, 8k",
                "shadowy fraudster in hoodie operating multiple laptops, dark cyber underground, red neon",
                "devastated victim looking at empty bank balance on phone, dramatic shadows",
                "glowing cybersecurity shield protecting a mobile phone, blue cyber defense theme"
            ]
        }


def main():
    feed_file = "scams.json"
    history = []

    if os.path.exists(feed_file):
        try:
            with open(feed_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "history" in data:
                    history = data["history"]
        except Exception as e:
            print(f"File read notice: {e}")

    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    existing_dates = {item.get("date") for item in history}

    if yesterday_str not in existing_dates and len(history) == 0:
        history.append(generate_day_report(yesterday))

    history = [item for item in history if item.get("date") != today_str]
    history.insert(0, generate_day_report(now))
    history = history[:30]

    with open(feed_file, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
            "history": history
        }, f, indent=2)

    if history:
        post_to_telegram(history[0])
        post_to_whatsapp(history[0])
        story_data = generate_scam_story(history[0])
        process_youtube_short(history[0], story_data)


    
    print("Pipeline completed successfully.")

if __name__ == "__main__":
    main()
