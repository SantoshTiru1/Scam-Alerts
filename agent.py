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

# Fast, stable inference model
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
        return response.choices[0].message.content
