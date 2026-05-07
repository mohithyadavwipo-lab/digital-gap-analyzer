import os
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Config
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

def scrape_technical_data(url):
    data = {"load_time": "N/A", "ssl": "No", "copyright": "N/A", "bi_tools": "No", "crm": "No", "socials": "No", "emails": "No", "raw_text": ""}
    try:
        if not url.startswith("http"): url = "https://" + url
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=15)
        data["load_time"] = f"{round(time.time() - start_time, 2)} seconds"
        data["ssl"] = "Yes" if response.url.startswith("https") else "No"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Grab more text for better context
        data["raw_text"] = soup.get_text(separator=' ', strip=True)[:6000]
        
        html_str = response.text.lower()
        if any(x in html_str for x in ["google-analytics", "gtm", "fbevents"]): data["bi_tools"] = "Yes"
        if any(x in html_str for x in ["hubspot", "salesforce", "zoho"]): data["crm"] = "Yes"
        if "mailto:" in html_str: data["emails"] = "Yes"
        if any(x in html_str for x in ["linkedin.com", "facebook.com", "twitter.com"]): data["socials"] = "Yes"
        
        import re
        match = re.search(r'©\s*(\d{4})', response.text)
        if match: data["copyright"] = match.group(1)
            
    except Exception as e:
        print(f"Scraper Error: {e}")
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url or not model: return jsonify({"error": "Config missing"}), 400

    tech_data = scrape_technical_data(url)
    
    # NEW AGGRESSIVE PROMPT
    prompt = f"""
    You are a Senior B2B Sales Strategist. Analyze the company at {url}.
    
    WEBSITE TEXT: {tech_data['raw_text']}
    
    INSTRUCTIONS:
    1. Use the provided text AND your vast internal knowledge about this company or similar companies in its sector.
    2. DO NOT USE "N/A" or "Data not found". Provide professional estimates based on industry standards if exact data is missing.
    3. Return ONLY a valid JSON object with these keys: 
       "company_name", "sector", "country", "established_year", "employees", "revenue", 
       "brief" (2 sentences), "sector_pain_points" (3 items), "company_pain_points" (3 items), "latest_news".
    """
    
    try:
        response = model.generate_content(prompt)
        import json
        # Robust JSON cleaning
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        biz_data = json.loads(clean_json)
    except Exception as e:
        print(f"AI Error: {e}")
        biz_data = {"company_name": url, "sector": "Analysis failed", "brief": "Please try running this URL again."}

    return jsonify({**tech_data, **biz_data})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
