import os
import json
from datetime import datetime
from duckduckgo_search import DDGS
from groq import Groq

# Initialize Groq client (reads GROQ_API_KEY from environment)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

REGIONS = [
    "North America",
    "South America",
    "Asia",
    "Europe",
    "Rest of the World"
]

def search_scam_news(region):
    query = f"cyber security scam phishing fraud news {region} {datetime.now().year}"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=3))
            if results:
                return results[0]
    except Exception as e:
        print(f"Search warning for {region}: {e}")
        
    return {
        "title": f"Ongoing Cyber Scam Warnings in {region}",
        "body": "Active phishing campaigns targeting consumers and enterprise credentials reported.",
        "url": "#"
    }

def summarize_scam(region, news_item):
    prompt = f"""
You are a cybersecurity threat analyst.
Region: {region}
Headline: {news_item.get('title')}
Context: {news_item.get('body')}

Task:
Write a clear, professional summary of this scam strictly in around 100 words.
Structure the summary:
1. Attack Vector (How the scam works)
2. Target Group
3. Prevention Tip
Do not exceed 120 words.
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a concise cybersecurity intelligence analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Error for {region}: {e}")
        return news_item.get('body', 'Summary unavailable.')

def main():
    feed = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "regions": {}
    }

    for region in REGIONS:
        print(f"Scraping & analyzing: {region}...")
        news = search_scam_news(region)
        summary = summarize_scam(region, news)

        feed["regions"][region] = {
            "headline": news.get("title"),
            "summary": summary,
            "source": news.get("url")
        }

    with open("scams.json", "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2)

    print("scams.json updated successfully.")

if __name__ == "__main__":
    main()
