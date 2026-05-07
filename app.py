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
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

def scrape_technical_data(url):
    data = {"load_time": "N/A", "ssl": "No", "copyright": "N/A", "bi_tools": "No", "crm": "No", "socials": "No", "emails": "No", "raw_text": "No text found"}
    try:
        if not url.startswith("http"): url = "https://" + url
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=15)
        data["load_time"] = f"{round(time.time() - start_time, 2)} seconds"
        data["ssl"] = "Yes" if response.url.startswith("https") else "No"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Filter out scripts and styles to get clean text for the AI
        for script in soup(["script", "style"]): script.extract()
        data["raw_text"] = soup.get_text(separator=' ', strip=True)[:7000]
        
        html_str = response.text.lower()
        if any(x in html_str for x in ["google-analytics", "gtm", "fbevents", "pixel"]): data["bi_tools"] = "Yes"
        if any(x in html_str for x in ["hubspot", "salesforce", "zoho", "crm"]): data["crm"] = "Yes"
        if "mailto:" in html_str: data["emails"] = "Yes"
        if any(x in html_str for x in ["linkedin.com", "facebook.com", "twitter.com"]): data["socials"] = "Yes"
        
        copy_match = re.search(r'©\s*(\d{4})', response.text)
        if copy_match: data["copyright"] = copy_match.group(1)
            
    except Exception as e:
        print(f"Scraper error: {e}")
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url or not model:
        return jsonify({"error": "Configuration Error"}), 400

    tech_data = scrape_technical_data(url)
    
    # FORCED INFERENCE PROMPT: This prevents the "N/A" results
    prompt = f"""
    Acting as a Senior Market Research Analyst, analyze the company: {url}
    
    Context from website: {tech_data['raw_text']}
    
    INSTRUCTIONS:
    1. Fill every field below. 
    2. If exact data (revenue/employees) is not in the text, use your internal knowledge of {url} or its sector to provide a professional estimate.
    3. DO NOT return "N/A", "Unknown", or "Data not found".
    4. Return ONLY a valid JSON object.
    
    JSON Template:
    {{
      "company_name": "Full Name",
      "sector": "Primary Industry",
      "country": "Headquarters Country",
      "established_year": "Year",
      "employees": "Count or Range",
      "revenue": "Estimate in USD",
      "brief": "2-sentence value proposition.",
      "sector_pain_points": ["Point 1", "Point 2", "Point 3"],
      "company_pain_points": ["Digital gap", "Operational gap", "Tech weakness"],
      "latest_news": "1 sentence on a recent trend or news."
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        # Clean potential markdown from AI response
        clean_json_str = response.text.replace('```json', '').replace('```', '').strip()
        biz_data = json.loads(clean_json_str)
    except Exception as e:
        print(f"AI Error: {e}")
        biz_data = {
            "company_name": url, "sector": "Analysis Pivot Required", "country": "Global",
            "established_year": "Various", "employees": "Review manually", "revenue": "Market dependent",
            "brief": "The tool encountered a processing error. Check website manually.",
            "sector_pain_points": ["Digital adoption lag", "Data silos", "Security risks"],
            "company_pain_points": ["Legacy systems", "Unoptimized UX", "Missing BI tools"],
            "latest_news": "Sector is undergoing rapid digital transformation."
        }

    return jsonify({**tech_data, **biz_data})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
