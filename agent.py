import os
import json
from datetime import datetime, timedelta
from duckduckgo_search import DDGS
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Optimized regional queries that reliably return news with valid URLs
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
            # 1. Try DuckDuckGo News first
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

            # 2. Fallback to standard web text search if news is empty
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

    # Safe fallback if search network fails
    return {
        "title": f"Active Cyber Fraud Campaign Target: {region}",
        "body": "Phishing threats impersonating financial and cloud services actively observed.",
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
    print(f"\n--- Gathering reports for {target_date} ---")
    day_entry = {
        "date": target_date.strftime("%Y-%m-%d"),
        "display_date": target_date.strftime("%B %d, %Y"),
        "regions": {}
    }
    for region in REGIONS.keys():
        print(f"Fetching: {region}...")
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

    # 1. Load existing history if available
    if os.path.exists(feed_file):
        try:
            with open(feed_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "history" in data:
                    history = data["history"]
                elif isinstance(data, dict) and "regions" in data:
                    # Convert old single-day format into history array
                    history = [{
                        "date": datetime.utcnow().strftime("%Y-%m-%d"),
                        "display_date": datetime.utcnow().strftime("%B %d, %Y"),
                        "regions": data["regions"]
                    }]
        except Exception as e:
            print(f"Reading existing json warning: {e}")

    existing_dates = {item["date"] for item in history}
    today = datetime.utcnow()
    today_str = today.strftime("%Y-%m-%d")
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    # 2. Seed "Yesterday" if brand new
    if yesterday_str not in existing_dates and len(history) == 0:
        history.append(generate_day_report(yesterday))

    # 3. Add or update "Today"
    history = [item for item in history if item["date"] != today_str]
    history.insert(0, generate_day_report(today))

    # Keep latest 30 days of records
    history = history[:30]

    with open(feed_file, "w", encoding="utf-8") as f:
        json.dump({"updated_at": today.strftime("%Y-%m-%d %H:%M UTC"), "history": history}, f, indent=2)

    print("scams.json updated successfully with daily history.")

if __name__ == "__main__":
    main()
