import os
import sys
import re
import json
import requests
import traceback
import time
from urllib.parse import urljoin, urlparse

# Try importing Google AI
try:
    import google.generativeai as genai
    from playwright.sync_api import sync_playwright
    print("DEBUG: Libraries imported successfully.")
except ImportError as e:
    print(f"DEBUG: Library Import Failed: {e}")

# --- CONFIGURATION ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("CRITICAL ERROR: GOOGLE_API_KEY is missing!")
else:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
    except Exception as e:
        print(f"DEBUG: Gemini Config Failed: {e}")

def get_working_model():
    # Priority: Gemini 1.5 Flash
    try:
        available_models = list(genai.list_models())
        for m in available_models:
            if 'gemini-1.5-flash' in m.name and 'latest' not in m.name:
                return m.name
        for m in available_models:
            if 'flash' in m.name and 'generateContent' in m.supported_generation_methods:
                return m.name
    except Exception as e:
        print(f"DEBUG: Model list failed: {e}")
    return "models/gemini-1.5-flash"

def get_page_content(url):
    print(f"DEBUG: Launching browser for {url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            page.wait_for_timeout(4000) 
            body_text = page.inner_text("body")
            content = page.content()
            browser.close()
            return body_text, content
        except Exception as e:
            browser.close()
            print(f"DEBUG: Browser Error: {e}")
            return "", ""

def extract_submit_url(html_content, model_name):
    print("DEBUG: Asking AI to find the Submit URL in HTML...")
    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        Analyze the HTML below and identify the URL where the answer should be POSTed.
        Return ONLY the URL. No markdown.
        HTML Snippet:
        {html_content[:8000]} 
        """
        response = model.generate_content(prompt)
        url = response.text.strip()
        match = re.search(r'(https?://[^\s"<>]+)', url)
        if match: return match.group(1)
        match_rel = re.search(r'(/[a-zA-Z0-9\-_]+)', url)
        if match_rel: return match_rel.group(1)
        return None
    except Exception as e:
        print(f"DEBUG: AI URL Extraction failed: {e}")
        return None

def llm_generate_solution(question_text, html_snippet, model_name, current_url):
    # SYSTEM PROMPT
    system_prompt = f"""
    You are a Python Data Analyst bot. 
    
    CURRENT PAGE URL: {current_url}
    
    CRITICAL RULES:
    1. **IMPORTS**: 
       - You MUST write all imports at the top of your script.
       - Example: `import pandas as pd`, `import requests`, `import speech_recognition`.
       - DO NOT assume libraries are already imported.
    
    2. **FILES & LINKS**: 
       - Look at the 'HTML Snippet' below to find the ACTUAL filenames (in href tags).
       - Do NOT guess 'data.csv'. Use the filename found in the HTML.
       - Combine relative links with the base URL using `urllib.parse.urljoin`.
    
    3. **SCRAPING TASKS**: 
       - If asked to "Scrape [LINK]", you must download that link.
       - Use `requests.get(full_url).text` to get the content.

    4. **SHELL COMMANDS**:
       - If the question asks to "Run a command" (like 'uv', 'pip', 'grep'), use `subprocess.run`.
       - Capture the output and set it to `result`.
    
    5. **OUTPUT**:
       - Write a complete Python script.
       - Define a variable `result` with the final answer.
       - Return ONLY valid Python code.
    """
    
    user_message = f"""
    Question: {question_text}
    
    HTML Snippet (Use this to find hrefs):
    {html_snippet[:4000]}
    """
    
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(f"{system_prompt}\n\n{user_message}")
        code = response.text.strip().replace("```python", "").replace("```", "")
        return code
    except Exception as e:
        print(f"DEBUG: LLM Generation Failed: {e}")
        return ""

def execute_generated_code(code_str):
    local_scope = {}
    try:
        # Import subprocess for the code execution context
        import subprocess
        exec(code_str, globals(), local_scope)
        return local_scope.get("result", "Error: No result var")
    except Exception as e:
        return f"Execution Error: {str(e)}"

def sanitize_answer(answer):
    try:
        if hasattr(answer, 'text') and hasattr(answer, 'status_code'): return answer.text
        if hasattr(answer, 'item'): return answer.item()
        if hasattr(answer, 'to_dict'): return str(answer)
        return answer
    except Exception as e:
        return str(answer)

def run_quiz_solver(start_url, email, secret):
    print(f"DEBUG: Starting solver for {start_url}", flush=True)
    model_name = get_working_model()
    print(f"DEBUG: Using model {model_name}")

    current_url = start_url
    steps = 0
    while current_url and steps < 15: # Increased step limit
        steps += 1
        print(f"--- Step {steps}: Processing {current_url} ---", flush=True)
        
        try:
            question_text, html_content = get_page_content(current_url)
            
            submit_url = None
            
            # 1. FIXED REGEX: Look for "POST ... to [URL]" (Broader match)
            match = re.search(r'POST.*to\s+(https?://[^\s"<>]+)', question_text, re.IGNORECASE)
            if match: 
                submit_url = match.group(1)
            
            # 2. Backup Regex: Look for any reference to a "submit" URL
            if not submit_url:
                match = re.search(r'(https?://[^\s"<>]+/submit)', html_content)
                if match: submit_url = match.group(1)

            # 3. AI Extraction
            if not submit_url:
                raw_url = extract_submit_url(html_content, model_name)
                if raw_url:
                    if raw_url.startswith("/"):
                        submit_url = urljoin(current_url, raw_url)
                    elif "http" in raw_url:
                        submit_url = raw_url

            # 4. Fallback Guess (Logic Fixed)
            if not submit_url or "project2" in submit_url:
                print("DEBUG: Extraction failed or invalid. Attempting Force Fallback to /submit")
                # Parse the domain and force /submit on the root
                parsed = urlparse(current_url)
                # Reconstruct: https:// + domain.com + /submit
                submit_url = f"{parsed.scheme}://{parsed.netloc}/submit"

            if submit_url:
                submit_url = submit_url.strip().strip(".").strip(",")

            print(f"DEBUG: Final Submit URL is {submit_url}")
            
            # GENERATE CODE
            code = llm_generate_solution(question_text, html_content, model_name, current_url)
            
            if not code:
                print("DEBUG: Failed to generate code. Skipping.")
                break
            
            print("DEBUG: Code generated. Executing...")
            raw_answer = execute_generated_code(code)
            answer = sanitize_answer(raw_answer)
            print(f"Calculated Answer (Sanitized): {answer}")
            
            payload = {"email": email, "secret": secret, "url": current_url, "answer": answer}
            
            print(f"DEBUG: Sending POST to {submit_url}")
            resp = requests.post(submit_url, json=payload, timeout=20)
            
            # SAFE JSON DECODING
            try:
                response_data = resp.json()
                print(f"Server Response: {response_data}")
            except json.JSONDecodeError:
                print(f"CRITICAL: Server returned non-JSON. Response Text: {resp.text[:200]}")
                break
            
            if response_data.get("correct") and "url" in response_data:
                current_url = response_data["url"]
            elif "url" in response_data:
                 print("DEBUG: Answer incorrect, but new URL provided. Moving on...")
                 current_url = response_data["url"]
            else:
                current_url = None
                
        except Exception as e:
            print(f"CRITICAL FAILURE: {traceback.format_exc()}", flush=True)
            break
