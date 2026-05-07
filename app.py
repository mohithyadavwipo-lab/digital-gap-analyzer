import os
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Configure Gemini API
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

def scrape_technical_data(url):
    data = {
        "load_time": "N/A", "ssl": "No", "copyright": "N/A", 
        "bi_tools": "No", "crm": "No", "socials": "No", "emails": "No", "raw_text": ""
    }
    try:
        if not url.startswith("http"):
            url = "https://" + url
            
        start_time = time.time()
        response = requests.get(url, timeout=10)
        data["load_time"] = f"{round(time.time() - start_time, 2)} seconds"
        data["ssl"] = "Yes" if response.url.startswith("https") else "No"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        data["raw_text"] = soup.get_text(separator=' ', strip=True)[:3500] 
        
        html_str = response.text.lower()
        if "google-analytics" in html_str or "fbevents" in html_str or "gtm" in html_str:
            data["bi_tools"] = "Yes (Analytics/Pixels Detected)"
        if "hubspot" in html_str or "salesforce" in html_str or "zoho" in html_str:
            data["crm"] = "Yes (CRM Scripts Detected)"
        if "mailto:" in html_str:
            data["emails"] = "Yes"
        if "facebook.com" in html_str or "linkedin.com" in html_str or "twitter.com" in html_str:
            data["socials"] = "Yes"
            
        # Try to find copyright year
        import re
        match = re.search(r'©\s*(\d{4})', response.text)
        if match:
            data["copyright"] = match.group(1)
            
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
    
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    tech_data = scrape_technical_data(url)
    
    prompt = f"""
    Analyze this website text scraped from {url}: {tech_data['raw_text']}
    Return ONLY a raw JSON object (no markdown formatting, no ```json tags) with these exact keys:
    "company_name", "sector", "country", "established_year", "employees", "revenue", 
    "brief" (a concise 2-sentence summary of what they do), 
    "sector_pain_points" (an array of 3 strings outlining general industry struggles), 
    "company_pain_points" (an array of 3 strings outlining specific tech/operational gaps), 
    "latest_news" (1 sentence of recent news or market context).
    If a specific data point like revenue or employees is completely unknown, use "Not publicly available".
    """
    
    try:
        gemini_response = model.generate_content(prompt)
        import json
        clean_json = gemini_response.text.replace('```json', '').replace('```', '').strip()
        biz_data = json.loads(clean_json)
    except Exception as e:
        biz_data = {"error": "Failed to extract business data."}

    final_output = {**tech_data, **biz_data}
    return jsonify(final_output)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
