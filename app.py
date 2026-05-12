import os
import time
import requests
import json
import re
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Core Configuration
api_key = os.environ.get("GEMINI_API_KEY")

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
    if not url or not api_key: return jsonify({"error": "Config missing"}), 400

    tech_data = scrape_technical_data(url)
    
    prompt = f"""
    You are a Senior B2B Intelligence Analyst and Sales Engineer. Analyze the company at {url}.
    Scraped text: {tech_data['raw_text']}
    
    INSTRUCTIONS:
    1. If the scraped text is short or blocked, use your internal training data to identify {url}.
    2. Identify the SPECIFIC country of origin (e.g., 'South Africa', 'India', 'USA'). Do NOT use 'Global'.
    3. Fill ALL fields with professional estimates based on industry standards. Do NOT leave fields blank.
    
    Output exactly and ONLY a JSON object:
    {{
      "company_name": "Name",
      "sector": "Sector",
      "country": "Specific Country",
      "employees": "Count Range",
      "revenue": "Revenue Estimate",
      "brief": "A comprehensive 4 to 5 sentence company profile detailing their core services, target market, and unique value proposition.",
      "sector_pain_points": ["Point 1", "Point 2", "Point 3"],
      "company_pain_points": ["Point 1", "Point 2", "Point 3"],
      "latest_news": "A detailed paragraph (3 to 4 sentences) explaining recent company news, strategic shifts, or major macro-market context impacting their specific business.",
      "email_draft": "Write a highly personalized B2B cold email following this EXACT structure and formatting, using line breaks (\\n\\n) between paragraphs:\\n\\nSubject: What if [insert specific sector pain point/dream outcome]?\\n\\nDear [Company Name] Team,\\n\\nBrightnodes is a blockchain, Web3, and AI software development company based in Bengaluru, India, partnering with [insert their specific sector] companies to [insert specific value outcome].\\n\\n[Write 1-2 sentences praising a specific recent achievement, initiative, or mission based on their profile]. \\n\\n[Write 1 sentence identifying a major operational challenge or structural friction point in their industry]. Brightnodes can build [insert tailored Web3/AI tech solution] that [insert direct business benefit without technical jargon].\\n\\n[Insert 1 real industry statistic showing ROI for this type of technology].\\n\\nWould you be open to a brief call this week to explore this further?\\n\\nWarm regards,\\nBrightnodes | brightnodes.io"
    }}
    """
    
    # Direct API call to the active 2026 model
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    
    try:
        res = requests.post(api_url, headers=headers, json=payload)
        res_data = res.json()
        
        # Catch direct API server errors
        if 'error' in res_data:
            raise ValueError(res_data['error']['message'])
            
        # Parse the raw text out of the standard Google JSON structure
        raw_text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Unbreakable JSON clip
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            clean_json_str = raw_text[start_idx:end_idx+1]
            biz_data = json.loads(clean_json_str)
            biz_data["match_score"] = "98/100"
        else:
            raise ValueError("No valid JSON structure found in AI response.")
            
    except Exception as e:
        print(f"FATAL API ERROR: {e}")
        biz_data = {
            "company_name": url,
            "sector": "Error Parsing Data",
            "country": "Error",
            "employees": "Error",
            "revenue": "Error",
            "brief": f"Direct API Error: {str(e)}",
            "sector_pain_points": ["Error", "Error", "Error"],
            "company_pain_points": ["Error", "Error", "Error"],
            "latest_news": "Error",
            "email_draft": "Error generating draft.",
            "match_score": "Error"
        }

    return jsonify({**tech_data, **biz_data})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
