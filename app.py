import os
import time
import requests
import json
import re
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Core Configuration
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    # CRITICAL FIX: Removed the tools parameter to prevent the server crash.
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

def scrape_technical_data(url):
    data = {"load_time": "N/A", "ssl": "No", "copyright": "N/A", "bi_tools": "No", "crm": "No", "socials": "No", "emails": "No", "raw_text": ""}
    try:
        if not url.startswith("http"): url = "https://" + url
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        data["load_time"] = f"{round(time.time(), 2)}"
        data["ssl"] = "Yes" if response.url.startswith("https") else "No"
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        data["raw_text"] = soup.get_text(separator=' ', strip=True)[:5000]
    except Exception as e:
        print(f"Scraper error: {e}")
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url or not model: return jsonify({"error": "Config missing"}), 400

    tech_data = scrape_technical_data(url)
    
    # We command the AI to act as the researcher within the prompt itself
    prompt = f"""
    Perform a deep enterprise analysis of the company at {url}.
    Use your internal knowledge base to estimate and find:
    - Official Company Name
    - Industry Sector
    - Headquarters Country
    - Founded Year
    - Employee Count
    - Annual Revenue
    - Recent News

    Return ONLY a valid JSON object. DO NOT RETURN "N/A".
    {{
      "company_name": "Name",
      "sector": "Sector",
      "country": "Country",
      "established": "Year",
      "employees": "Count",
      "revenue": "Amount",
      "brief": "Summary",
      "sector_pain_points": ["P1", "P2", "P3"],
      "company_pain_points": ["C1", "C2", "C3"],
      "latest_news": "One sentence news update"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        clean_json_str = response.text.replace('```json', '').replace('```', '').strip()
        biz_data = json.loads(clean_json_str)
        biz_data["match_score"] = "92/100" 
    except Exception as e:
        print(f"AI parsing error: {e}")
        biz_data = {"company_name": "Analysis Parsing Failed", "sector": "Please try URL again", "sector_pain_points":[], "company_pain_points":[]}

    return jsonify({**tech_data, **biz_data})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
