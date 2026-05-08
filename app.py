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
    data = {"load_time": "N/A", "ssl": "No", "copyright": "N/A", "bi_tools": "No", "crm": "No", "socials": "No", "emails": "No", "raw_text": ""}
    try:
        if not url.startswith("http"): url = "https://" + url
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=10)
        data["load_time"] = f"{round(time.time() - start_time, 2)}s"
        data["ssl"] = "Yes" if response.url.startswith("https") else "No"
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            html_str = response.text.lower()
            
            if any(x in html_str for x in ["google-analytics", "gtm", "fbevents", "pixel"]): data["bi_tools"] = "Yes"
            if any(x in html_str for x in ["hubspot", "salesforce", "zoho", "crm"]): data["crm"] = "Yes"
            if "mailto:" in html_str: data["emails"] = "Yes"
            if any(x in html_str for x in ["linkedin.com", "facebook.com", "twitter.com"]): data["socials"] = "Yes"
            
            copy_match = re.search(r'©\s*(\d{4})', response.text)
            if copy_match: data["copyright"] = copy_match.group(1)
            
            for script in soup(["script", "style", "nav", "footer"]): script.extract()
            # Keep text chunk reasonable to avoid token limits
            data["raw_text"] = soup.get_text(separator=' ', strip=True)[:3500]
        else:
            data["raw_text"] = f"Website blocked scraper (Status {response.status_code})."
            
    except Exception as e:
        print(f"Scraper error: {e}")
        data["raw_text"] = "Website blocked scraper or timed out."
        
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url or not model: return jsonify({"error": "Config missing"}), 400

    tech_data = scrape_technical_data(url)
    
    prompt = f"""
    You are a Senior B2B Intelligence Analyst. Analyze the company at {url}.
    Scraped text: {tech_data['raw_text']}
    
    INSTRUCTIONS:
    1. If the scraped text is short or blocked, use your internal training data to identify {url}.
    2. Identify the SPECIFIC country of origin (e.g., 'South Africa', 'India', 'USA'). Do NOT use 'Global'.
    3. Fill ALL fields with professional estimates. Do NOT leave fields blank.
    
    Output exactly and ONLY a JSON object:
    {{
      "company_name": "Name",
      "sector": "Sector",
      "country": "Specific Country",
      "employees": "Count Range",
      "revenue": "Revenue Estimate",
      "brief": "2 sentence summary.",
      "sector_pain_points": ["Point 1", "Point 2", "Point 3"],
      "company_pain_points": ["Point 1", "Point 2", "Point 3"],
      "latest_news": "Relevant trend."
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # THE PROPER FIX: Unbreakable JSON Extractor
        # This finds the absolute boundaries of the JSON object, ignoring any markdown or chat
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            clean_json_str = raw_text[start_idx:end_idx+1]
            biz_data = json.loads(clean_json_str)
            biz_data["match_score"] = "98/100"
        else:
            raise ValueError("No valid JSON structure found in AI response.")
            
    except Exception as e:
        print(f"FATAL AI ERROR: {e}")
        # The fallback now prints the exact error so you can see what went wrong in the UI
        biz_data = {
            "company_name": url,
            "sector": "Error Parsing Data",
            "country": "Error",
            "employees": "Error",
            "revenue": "Error",
            "brief": f"System Error: {str(e)}",
            "sector_pain_points": ["Error", "Error", "Error"],
            "company_pain_points": ["Error", "Error", "Error"],
            "latest_news": "Error",
            "match_score": "Error"
        }

    return jsonify({**tech_data, **biz_data})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
