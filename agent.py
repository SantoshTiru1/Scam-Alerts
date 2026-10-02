import os
import json
from datetime import datetime, timedelta
from duckduckgo_search import DDGS
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

REGIONS = {
    "North America": ["North America cyber scam phishing", "US cyber fraud breach FBI"],
    "South America": ["Latin America cyber scam fraud", "Brazil South America cyber phishing"],
    "Asia": ["Asia cyber scam phishing news", "Singapore India cyber fraud scam"],
    "Europe": ["Europe cyber scam fraud phishing", "UK Europe cyber attack scam"],
    "Rest of the World": ["Global cyber security scam", "Australia Africa cyber fraud scam"]
}

def search_scam_news(region):
    search_terms = REGIONS.get(region, [f"{region} cyber scam"])
    with DDGS() as ddgs:
        for term in search_terms:
            # 1. Try DuckDuckGo News
            try:
                news_results = list(ddgs.news(term, max_results=3))
                if news_results:
                    item = news_results[0]
                    url = item.get("url") or item.get("href") or item.get("link")
                    if url and url.startswith("http"):
                        return {
                            "title": item.get("title", f"{region} Cyber Alert"),
                            "body": item.get("body", "Scam alert details reported."),
                            "url": url
                        }
            except Exception:
                pass

            # 2. Try Web Search
            try:
                text_results = list(ddgs.text(term, max_results=3))
                if text_results:
                    item = text_results[0]
                    url = item.get("href") or item.get("url")
                    if url and url.startswith("http"):
                        return {
                            "title": item.get("title", f"{region} Threat Report"),
                            "body": item.get("body", "Phishing and credential fraud reported."),
                            "url": url
                        }
            except Exception:
                pass

    return {
        "title": f"Active Cyber Scam Activity in {region}",
        "body": "Active phishing campaigns targeting consumers and cloud credentials reported.",
        "url": f"https://www.google.com/search?q={region}+cyber+scam"
    }

def summarize_scam(region, news_item):
    prompt = f"""
You are a cybersecurity threat analyst.
Region: {region}
Headline: {news_item.get('title')}
Context: {news_item.get('body')}

Task:
Write a summary strictly in around 100 words.
Structure:
- Threat Vector: How the scam operates
- Target: Who is targeted
- Mitigation: How to stay safe
Keep it under 110 words.
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a concise cyber intelligence analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Error for {region}: {e}")
        return news_item.get("body", "Summary unavailable.")

def generate_day_report(target_date):
    print(f"--- Fetching news for {target_date.strftime('%Y-%m-%d')} ---")
    day_entry = {
        "date": target_date.strftime("%Y-%m-%d"),
        "regions": {}
    }
    for region in REGIONS.keys():
        print(f"Scraping & analyzing: {region}...")
        news = search_scam_news(region)
        summary = summarize_scam(region, news)
        day_entry["regions"][region] = {
            "headline": news.get("title"),
            "summary": summary,
            "source": news.get("url")
        }
    return day_entry

def main():
    feed_file = "scams.json"
    history = []

    # 1. Read existing data and handle both old and new schemas
    if os.path.exists(feed_file):
        try:
            with open(feed_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "history" in data and isinstance(data["history"], list):
                        history = data["history"]
                    elif "regions" in data and data["regions"]:
                        # Convert old flat format into history
                        history.append({
                            "date": datetime.utcnow().strftime("%Y-%m-%d"),
                            "regions": data["regions"]
                        })
        except Exception as e:
            print(f"File read error: {e}")

    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    existing_dates = {item.get("date") for item in history}

    # 2. Add Yesterday if not present
    if yesterday_str not in existing_dates:
        history.append(generate_day_report(yesterday))

    # 3. Add or refresh Today
    history = [item for item in history if item.get("date") != today_str]
    history.insert(0, generate_day_report(now))

    # Keep latest 30 days
    history = history[:30]

    with open(feed_file, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
            "history": history
        }, f, indent=2)

    print("scams.json written successfully with history format.")

if __name__ == "__main__":
    main()
