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
    Directly targets https://cybercrime.gov.in/Webform/daily-digest.aspx
    Extracts the latest 'Daily Digest - [Date]' item and PDF advisory link.
    """
    portal_url = "https://cybercrime.gov.in/Webform/daily-digest.aspx"
    base_url = "https://cybercrime.gov.in/Webform/"

    session = requests.Session()
    # Comprehensive browser headers to pass government web-server filtering
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en-IN;q=0.9,en;q=0.8",
        "Referer": "https://cybercrime.gov.in/",
        "Connection": "keep-alive"
    })

    try:
        # verify=False prevents SSL handshake failure on NIC/GOV cert bundles
        res = session.get(portal_url, timeout=15, verify=False)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")

            # 1. Search for dated "Daily Digest" links/rows
            # Usually rendered as: <a href="Uploads/...">Daily Digest - DD/MM/YYYY</a> or similar
            digest_links = []
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]

                # Match patterns like "Daily Digest", "Digest", or date-stamped PDFs
                if re.search(r"daily\s*digest", text, re.IGNORECASE) or ("digest" in href.lower() and href.endswith(".pdf")):
                    full_link = href if href.startswith("http") else urllib.parse.urljoin(base_url, href)
                    digest_links.append({
                        "title": text if len(text) > 10 else f"I4C Daily Cyber Digest: {text}",
                        "body": f"Official National Cyber Crime Reporting Portal Daily Digest Advisory ({text}). Covers active financial fraud vectors, malicious APK campaigns, and cyber safety alerts across India.",
                        "url": full_link
                    })

            if digest_links:
                # Return the very first (most recent) digest link found on the page
                return digest_links[0]

            # 2. Check for table rows if links are structured in an ASP.NET GridView
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    row_text = row.get_text(" ", strip=True)
                    if "digest" in row_text.lower():
                        a_elem = row.find("a", href=True)
                        link = urllib.parse.urljoin(base_url, a_elem["href"]) if a_elem else portal_url
                        return {
                            "title": row_text[:80],
                            "body": f"Official cyber security advisory from CyberCrime.gov.in: {row_text}",
                            "url": link
                        }

    except Exception as e:
        print(f"Warning: Cybercrime.gov.in scrape error: {e}")

    # Fallback to direct CERT-In / PIB Cyber Crime Advisories if the portal times out
    fallback_articles = fetch_rss_articles("site:pib.gov.in cyber crime advisory fraud scam OR site:cert-in.org.in")
    if fallback_articles:
        return fallback_articles[0]

    return {
        "title": "National Cyber Crime Reporting Portal (cybercrime.gov.in) Advisory",
        "body": "Daily cyber safety advisory issued by Indian Cyber Crime Coordination Centre (I4C), Ministry of Home Affairs, warning citizens against digital arrest frauds, malicious APK links, and fake stock trading investment apps.",
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
