import os
import sys
import re
import json
import requests
import traceback
import time
from urllib.parse import urljoin

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
    try:
        print("DEBUG: Checking available models...")
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
            page.wait_for_timeout(5000) 
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
        if match:
            return match.group(1)
        # Check for relative paths like /submit
        match_rel = re.search(r'(/[a-zA-Z0-9\-_]+)', url)
        if match_rel:
            return match_rel.group(1)
        return None
    except Exception as e:
        print(f"DEBUG: AI URL Extraction failed: {e}")
        return None

def llm_generate_solution(question_text, model_name, current_url):
    # UPDATED PROMPT: We now pass the current_url so it resolves links correctly
    system_prompt = f"""
    You are a Python Data Analyst bot. 
    
    CONTEXT:
    The current page URL is: {current_url}
    If you see relative links (like '/demo-scrape-data'), you MUST resolve them against the current page URL using 'urllib.parse.urljoin'.
    
    GOAL:
    1. Write a Python script to solve the problem.
    2. Define a variable 'result' with the final answer.
    3. 'result' MUST be a string, integer, or boolean.
    4. If downloading a file, use 'requests'.
    
    Return ONLY valid Python code.
    """
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(f"{system_prompt}\n\nQuestion: {question_text}")
        code = response.text.strip().replace("```python", "").replace("```", "")
        return code
    except Exception as e:
        print(f"DEBUG: LLM Generation Failed: {e}")
        return ""

def execute_generated_code(code_str):
    local_scope = {}
    try:
        exec(code_str, globals(), local_scope)
        return local_scope.get("result", "Error: No result var")
    except Exception as e:
        return f"Execution Error: {str(e)}"

def sanitize_answer(answer):
    try:
        if hasattr(answer, 'text') and hasattr(answer, 'status_code'):
            return answer.text
        if hasattr(answer, 'item'):
            return answer.item()
        if hasattr(answer, 'to_dict'):
            return str(answer)
        return answer
    except Exception as e:
        return str(answer)

def run_quiz_solver(start_url, email, secret):
    print(f"DEBUG: Starting solver for {start_url}", flush=True)
    model_name = get_working_model()
    print(f"DEBUG: Using model {model_name}")

    current_url = start_url
    steps = 0
    while current_url and steps < 10:
        steps += 1
        print(f"--- Step {steps}: Processing {current_url} ---", flush=True)
        
        try:
            question_text, html_content = get_page_content(current_url)
            print(f"DEBUG: HTML Snippet: {html_content[:200]}...")
            
            submit_url = None
            
            # Strategy A: Regex
            match = re.search(r'Post.*answer.*(https?://[^\s"<>]+)', question_text, re.IGNORECASE)
            if match:
                submit_url = match.group(1)
            
            # Strategy B: AI
            if not submit_url:
                raw_url = extract_submit_url(html_content, model_name)
                if raw_url:
                    # If AI returns a relative path like /submit, join it
                    if raw_url.startswith("/"):
                        submit_url = urljoin(current_url, raw_url)
                    elif "http" in raw_url:
                        submit_url = raw_url

            # Strategy C: Fallback Guess
            if not submit_url:
                print("DEBUG: Extraction failed. Attempting Fallback to /submit")
                # Clean base URL logic
                parsed = re.match(r'(https?://[^/]+)', current_url)
                if parsed:
                    submit_url = parsed.group(1) + "/submit"
                    print(f"DEBUG: Guessed Fallback URL: {submit_url}")

            if submit_url:
                submit_url = submit_url.strip().strip(".").strip(",")

            print(f"DEBUG: Final Submit URL is {submit_url}")
            
            # Pass current_url to the LLM so it knows the base domain
            code = llm_generate_solution(question_text, model_name, current_url)
            
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
            print(f"Server Response: {resp.json()}")
            
            data = resp.json()
            if data.get("correct") and "url" in data:
                current_url = data["url"]
            elif "url" in data:
                 # Even if wrong, if they gave us a new URL, take it (Skip logic)
                 print("DEBUG: Answer incorrect, but new URL provided. Moving on...")
                 current_url = data["url"]
            else:
                current_url = None
                
        except Exception as e:
            print(f"CRITICAL FAILURE: {traceback.format_exc()}", flush=True)
            break
