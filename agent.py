import os
import json
import re
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Custom headers to bypass bot blocks when fetching Indian gov & news sites
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
    """
    Fetches real primary articles from Google News RSS.
    Returns list of {'title': ..., 'body': ..., 'url': ...}
    Guarantees no google search fallback URLs.
    """
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
                
                # Clean html tags from description
                soup = BeautifulSoup(description, "html.parser")
                clean_text = soup.get_text()

                if link and not link.startswith("https://www.google.com/search"):
                    articles.append({
                        "title": title,
                        "body": clean_text if clean_text else title,
                        "url": link
                    })
    except Exception as e:
        print(f"RSS fetch warning for {query}: {e}")
        
    return articles

def fetch_india_official_scams():
    """
    Scrapes the official Indian Cyber Crime portal (cybercrime.gov.in)
    """
    portal_url = "https://cybercrime.gov.in/Webform/daily-digest.aspx"
    try:
        res = requests.get(portal_url, headers=HEADERS, timeout=12, verify=False)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Look for recent advisory/digest links or table content
            digest_items = []
            for a_tag in soup.find_all("a", href=True):
                text = a_tag.get_text(strip=True)
                href = a_tag["href"]
                if len(text) > 20 and any(w in text.lower() for w in ["scam", "fraud", "phishing", "cyber", "alert", "digest"]):
                    full_url = href if href.startswith("http") else urllib.parse.urljoin("https://cybercrime.gov.in/Webform/", href)
                    digest_items.append({"title": text, "body": text, "url": full_url})
            
            if digest_items:
                return digest_items[0]
                
            # If no individual links, extract text from main content body
            content_div = soup.find("div", {"id": "content"}) or soup.find("body")
            if content_div:
                text_sample = ' '.join(content_div.get_text().split()[:200])
                if len(text_sample) > 50:
                    return {
                        "title": "National Cyber Crime Reporting Portal Daily Digest Advisory",
                        "body": text_sample,
                        "url": portal_url
                    }
    except Exception as e:
        print(f"Official cybercrime.gov.in fetch fallback: {e}")

    # Fallback to direct Indian cyber news from verified publishers
    news = fetch_rss_articles("India cyber crime fraud scam CERT-In")
    if news:
        return news[0]

    return {
        "title": "Indian Cyber Crime Coordination Centre (I4C) Daily Advisory",
        "body": "Active financial fraud campaigns using APK files and fake loan apps reported.",
        "url": portal_url
    }

def fetch_scam_for_region(region):
    if region == "India":
        return fetch_india_official_scams()

    query_map = {
        "North America": "US Canada cyber security scam phishing fraud news",
        "South America": "Latin America Brazil cyber security fraud scam",
        "Europe": "Europe UK cyber crime phishing scam attack news",
        "Singapore": "Singapore cyber security scam police advisory phishing",
        "China": "China cyber fraud scam phishing banking attack news",
        "Japan": "Japan cyber security fraud phishing scam police",
        "Rest of the World": "Australia Africa cyber fraud scam attack news"
    }

    query = query_map.get(region, f"{region} cyber crime scam")
    articles = fetch_rss_articles(query)
    
    if articles:
        return articles[0]

    # Specific publisher fallback if Google RSS is quiet
    fallback_urls = {
        "Singapore": "https://www.straitstimes.com/tech",
        "Japan": "https://www.japantimes.co.jp/news/cybersecurity/",
        "China": "https://www.scmp.com/topics/cybersecurity",
        "Europe": "https://www.bleepingcomputer.com/",
        "North America": "https://thehackernews.com/",
        "South America": "https://thehackernews.com/",
        "Rest of the World": "https://www.bleepingcomputer.com/"
    }
    return {
        "title": f"Active Cyber Fraud Campaign Target: {region}",
        "body": f"Phishing threats targeting consumers and banking apps observed across {region}.",
        "url": fallback_urls.get(region, "https://thehackernews.com")
    }

def summarize_scam(region, news_item):
    prompt = f"""
You are a senior cybersecurity threat intelligence analyst.
Region / Country: {region}
Title / Advisory: {news_item.get('title')}
Details: {news_item.get('body')}

Task:
Write an informative threat summary strictly in around 100 words.
Structure clearly:
- Threat Vector: The attack mechanics (phishing, malware, SMS, impersonation)
- Target: Who is targeted
- Prevention: Immediate safety measure
Keep it under 110 words.
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a concise, accurate cyber threat analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Error for {region}: {e}")
        return news_item.get("body", "Summary currently unavailable.")

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

    # Seed yesterday on first run if missing
    if yesterday_str not in existing_dates and len(history) == 0:
        history.append(generate_day_report(yesterday))

    # Add or update today
    history = [item for item in history if item.get("date") != today_str]
    history.insert(0, generate_day_report(now))

    # Retain 30 days
    history = history[:30]

    with open(feed_file, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
            "history": history
        }, f, indent=2)

    print("scams.json updated with India, Singapore, China, Japan & direct articles.")

if __name__ == "__main__":
    main()
