import os
import json
import re
import random
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup
from groq import Groq
from youtube_agent import process_youtube_short

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# 37 Official & Emerging Cyber Threat Categories
CATEGORIES_37 = [
    "Illegal Betting & Online Casino Scams",
    "Digital Arrest & Fake Police Video Calls",
    "Part-Time Job & Telegram Rating Tasks",
    "Fake Stock Trading Apps & Pre-IPO Scams",
    "Sextortion & WhatsApp Video Blackmail",
    "Malicious APK & Fake Utility Bills",
    "SIM Swapping & OTP Interception",
    "Fake Courier & Customs Drug Parcels",
    "Instant Loan Apps & Contact List Extortion",
    "AI Voice Cloning & Fake Kidnapping",
    "Deepfake Executive & CEO Fraud",
    "Crypto Pig Butchering (Sha Zhu Pan)",
    "Credit Card Reward Points Phishing",
    "Electricity Bill Disconnection Threat",
    "Matrimonial & Romance Bait Scams",
    "Fake E-Challan & Traffic Fine APKs",
    "Work From Home YouTube Like Scams",
    "Fake Airline Ticket & Hotel Cancellation",
    "ATM Card Skimming & POS Cloning",
    "Aadhaar Enabled Payment System (AePS) Fraud",
    "Lottery & KBC Lucky Draw WhatsApp Scams",
    "Fake Customer Care & AnyDesk Screen Sharing",
    "Student Visa & Overseas Job Offer Fraud",
    "QR Code Scanning Payment Reversal Trap",
    "Fake Bank KYC Update SMS Links",
    "Government Subsidy & Free Recharge Links",
    "Fake E-Commerce Deals & Clone Stores",
    "Charity & Disaster Relief Fund Scams",
    "Fake Investment Guru WhatsApp Groups",
    "Phishing Emails with Password-Protected Zips",
    "Fake Delivery Address Confirmation Links",
    "Ransomware & LockBit Extortion",
    "Fake Hospital Emergency & Blood Request Trap",
    "Identity Theft Using Leaked PAN & Aadhaar",
    "Public Wi-Fi Man-in-the-Middle Attacks",
    "Fake Tech Support Blue Screen Popup",
    "Rental Property Deposit & Advance Fraud"
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

REGIONS = [
    "India",
    "North America",
    "South America",
    "Europe",
    "Singapore",
    "China",
    "Japan",
    "Rest of the World"
]

def query_groq(messages, temperature=0.7, max_tokens=650):
    last_err = None
    for model in GROQ_MODELS:
        try:
            res = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Groq models failed. Last error: {last_err}")

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
    fallback_articles = fetch_rss_articles("India cyber crime scam phishing digital arrest fraud")
    if fallback_articles:
        return fallback_articles[0]

    return {
        "title": "National Cyber Crime Reporting Advisory",
        "body": "Active financial fraud campaigns using malicious APK links and digital arrest threats reported.",
        "url": "https://cybercrime.gov.in"
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
        return query_groq([
            {"role": "system", "content": "You are a concise cyber intelligence analyst."},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=220)
    except Exception as e:
        print(f"LLM Error for {region}: {e}")
        return news_item.get("body", "Summary currently unavailable.")

def post_to_telegram(day_entry):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    date_str = day_entry.get("date", "Today")
    regions_data = day_entry.get("regions", {})
    message = f"🚨 *Global Cyber Scam Alert — {date_str}*\n\n"

    for region, info in regions_data.items():
        headline = info.get("headline", f"{region} Alert")
        summary = info.get("summary", "").replace("*", "").split("\n")[0]
        source = info.get("source", "")
        message += f"🌍 *{region}*: {headline}\n_{summary}_\n"
        if source and source != "#":
            message += f"[🔗 Read Primary Report]({source})\n"
        message += "\n"

    message += "🌐 *Full Matrix:* https://santoshtiru1.github.io/Scam-Alerts/"
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=15)
    except Exception as e:
        print(f"Telegram send notice: {e}")

def post_to_whatsapp(day_entry):
    phone = os.getenv("WHATSAPP_PHONE")
    apikey = os.getenv("WHATSAPP_APIKEY")
    if not phone or not apikey:
        return

    date_str = day_entry.get("date", "Today")
    regions = day_entry.get("regions", {})
    msg = f"🚨 *Global Cyber Scam Digest — {date_str}*\n\n"
    for reg in ["India", "Singapore", "North America", "Europe"]:
        if reg in regions:
            msg += f"• *{reg}*: {regions[reg].get('headline', '')[:75]}\n"
    msg += "\n🌐 https://santoshtiru1.github.io/Scam-Alerts/"

    try:
        requests.get(f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={urllib.parse.quote(msg)}&apikey={apikey}", timeout=15)
    except Exception as e:
        print("WhatsApp notice:", e)

def generate_day_report(target_date):
    print(f"\n--- Gathering reports for {target_date.strftime('%Y-%m-%d')} ---")
    day_entry = {
        "date": target_date.strftime("%Y-%m-%d"),
        "regions": {}
    }
    for region in REGIONS:
        item = fetch_scam_for_region(region)
        summary = summarize_scam(region, item)
        day_entry["regions"][region] = {
            "headline": item.get("title"),
            "summary": summary,
            "source": item.get("url")
        }
    return day_entry

def select_unused_category(history):
    past_7_categories = set()
    for entry in history[:7]:
        cat = entry.get("featured_category")
        if cat:
            past_7_categories.add(cat)

    eligible_categories = [c for c in CATEGORIES_37 if c not in past_7_categories]
    if not eligible_categories:
        eligible_categories = CATEGORIES_37

    selected_category = random.choice(eligible_categories)
    print(f"\n[Category Selection] Past 7 days avoided: {past_7_categories}")
    print(f"[Category Selection] Chosen category for today: {selected_category}")
    return selected_category

def generate_cinematic_story(day_entry, chosen_category):
    regions = day_entry.get("regions", {})
    context_news = []
    for reg, data in regions.items():
        context_news.append(f"[{reg}]: {data.get('headline')} - {data.get('summary')}")
    combined_context = "\n".join(context_news[:4])

    prompt = f"""
You are writing a gripping true-crime dialogue for YouTube Shorts.

CORE CATEGORY: {chosen_category}

TODAY CONTEXT:
{combined_context}

CHARACTERS:
- MAYA (Investigative Reporter - Urgent, reports the trap and victim loss)
- VIKRAM (Lead Cyber Intelligence Analyst - Authoritative, explains technical trick & single defense rule)

RULES:
1. Write an alternating 4-line spoken dialogue (90 to 110 words total).
2. Exactly 4 turns:
   - Line 1 (Maya): Breaks the alarming incident for {chosen_category}.
   - Line 2 (Vikram): Explains the technical trap used by scammers.
   - Line 3 (Maya): Details how fast funds were lost.
   - Line 4 (Vikram): Delivers the clear rule to avoid getting scammed.
3. Return STRICT JSON with keys "title", "dialogue", "category", "video_queries".

Example JSON format:
{{
  "title": "Shocking Title under 60 chars",
  "category": "{chosen_category}",
  "dialogue": [
    {{"speaker": "Maya", "text": "..."}},
    {{"speaker": "Vikram", "text": "..."}},
    {{"speaker": "Maya", "text": "..."}},
    {{"speaker": "Vikram", "text": "..."}}
  ],
  "video_queries": ["query1", "query2", "query3", "query4"]
}}
"""
    try:
        raw = query_groq([
            {"role": "system", "content": "You are a master scriptwriter. Return valid raw JSON only."},
            {"role": "user", "content": prompt}
        ], temperature=0.8, max_tokens=650)

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        data["category"] = chosen_category
        return data
    except Exception as e:
        print(f"LLM generation warning: {e}. Building targeted procedural script.")
        return {
            "title": f"The {chosen_category} Trap",
            "category": chosen_category,
            "dialogue": [
                {"speaker": "Maya", "text": f"Vikram, syndicate rings running {chosen_category} just targeted thousands of accounts overnight."},
                {"speaker": "Vikram", "text": "They exploit trust through spoofed credentials and manipulated interfaces to bypass ordinary defenses."},
                {"speaker": "Maya", "text": "Victims had their savings wiped within minutes before discovering the entire platform was fabricated."},
                {"speaker": "Vikram", "text": "Never authorize payments or install unauthorized profiles based on unverified urgency. Cut communication immediately."}
            ],
            "video_queries": ["hacker dark room", "cyber technology code", "smartphone hacking screen", "police sirens night"]
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

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_str = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    existing_dates = {item.get("date") for item in history}

    if yesterday_str not in existing_dates and len(history) == 0:
        history.append(generate_day_report(yesterday))

    history = [item for item in history if item.get("date") != today_str]
    today_report = generate_day_report(now)

    # 1. Select a category not covered in the past 7 days
    chosen_category = select_unused_category(history)
    today_report["featured_category"] = chosen_category

    # 2. Generate a fresh story for today's video
    story_data = generate_cinematic_story(today_report, chosen_category)

    # 3. Save into history and immediately WRITE TO DISK (Ensures web page is updated)
    history.insert(0, today_report)
    history = history[:30]

    with open(feed_file, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
            "history": history
        }, f, indent=2)
    print(f"Successfully saved updated {feed_file}!")

    # 4. Broadcast alerts
    post_to_telegram(history[0])
    post_to_whatsapp(history[0])

    # 5. Process YouTube Short with safe error handling
    try:
        process_youtube_short(history[0], story_data)
    except Exception as e:
        print(f"YouTube processing error (non-fatal for web feed): {e}")

    print("Pipeline completed.")

if __name__ == "__main__":
    main()
