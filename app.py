import os
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# Safely get the API key from Render's environment variables
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    # Using 1.5-flash for the best balance of speed and reasoning
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("WARNING: GEMINI_API_KEY environment variable is missing!")
    model = None

def scrape_technical_data(url):
    data = {
        "load_time": "N/A", "ssl": "No", "copyright": "N/A", 
        "bi_tools": "No", "crm": "No", "socials": "No", "emails": "No", "raw_text": ""
    }
    try:
        if not url.startswith("http"):
            url = "https://" + url
            
        start_time = time.time()
        # User-Agent makes our scraper look like a real browser to avoid being blocked
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        data["load_time"] = f"{round(time.time() - start_time, 2)} seconds"
        data["ssl"] = "Yes" if response.url.startswith("https") else "No"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # We grab a larger chunk of text (up to 5000 chars) for better AI context
        data["raw_text"] = soup.get_text(separator=' ', strip=True)[:5000] 
        
        html_str = response.text.lower()
        # Checking for common Business Intelligence and CRM footprints
        if any(tool in html_str for tool in ["google-analytics", "fbevents", "gtm", "hotjar"]):
            data["bi_tools"] = "Yes (Analytics/Pixels Detected)"
        if any(crm in html_str for crm in ["hubspot", "salesforce", "zoho", "intercom", "zendesk"]):
            data["crm"] = "Yes (CRM/Automation Detected)"
        if "mailto:" in html_str:
            data["emails"] = "Yes"
        if any(social in html_str for social in ["facebook.com", "linkedin.com", "twitter.com", "instagram.com"]):
            data["socials"] = "Yes"
            
        # Extracting the copyright year from the footer text
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

    # 1. Run the technical scraper
    tech_data = scrape_technical_data(url)
    
    if not model:
        return jsonify({"error": "Gemini API key is missing on Render settings."}), 500
    
    # 2. Enhanced Prompt: Directing Gemini to be a Senior Market Researcher
    prompt = f"""
    You are a Senior Market Research Analyst focusing on Digital Transformation. 
    I have scraped the following text from the website {url}: 
    
    --- START SCRAPED TEXT ---
    {tech_data['raw_text']}
    --- END SCRAPED TEXT ---
    
    Based on the text above AND your extensive internal knowledge of the company {url} and its industry, 
    provide a comprehensive business analysis. 
    
    Return ONLY a raw JSON object (no markdown, no backticks) with these exact keys:
    "company_name": "Official name",
    "sector": "The specific industry sector",
    "country": "Primary headquarters location",
    "established_year": "Year founded (use your knowledge if not in text)",
    "employees": "Estimated headcount (e.g., 500-1000)",
    "revenue": "Estimated annual revenue (e.g., $10M-$50M) or business scale",
    "brief": "A professional 2-sentence summary of their core services.",
    "sector_pain_points": ["Pain point 1", "Pain point 2", "Pain point 3"],
    "company_pain_points": ["Specific tech/digital gap", "Strategic weakness", "Competitive threat"],
    "latest_news": "A recent milestone, product launch, or industry-relevant news item."
    
    CRITICAL: Do not return "N/A" or "Not available". Use your expert context to provide the most 
    accurate professional estimates possible for {url}.
    """
    
    try:
        # Generate the business data using the AI
        gemini_response = model.generate_content(prompt)
        import json
        # Clean the response to ensure it's valid JSON
        clean_json = gemini_response.text.replace('```json', '').replace('```', '').strip()
        biz_data = json.loads(clean_json)
    except Exception as e:
        print(f"AI Extraction Error: {e}")
        biz_data = {"error": "AI could not process this company."}

    # Combine the direct technical scraper data with the AI's business analysis
    final_output = {**tech_data, **biz_data}
    return jsonify(final_output)

if __name__ == '__main__':
    # Using 0.0.0.0 is required for Render to route external traffic to the app
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
