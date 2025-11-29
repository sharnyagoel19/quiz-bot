import os
import sys
import re
import json
import requests
import traceback

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
    """
    Dynamically asks Google: 'What models can I use?'
    and returns the first valid one.
    """
    try:
        print("DEBUG: Listing available models...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name:
                    print(f"DEBUG: Found valid model: {m.name}")
                    return m.name
    except Exception as e:
        print(f"DEBUG: Could not list models: {e}")
    
    # Fallback if list fails
    return "models/gemini-1.5-flash"

def get_page_content(url):
    print(f"DEBUG: Launching browser for {url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            page.wait_for_timeout(2000)
            body_text = page.inner_text("body")
            content = page.content()
            browser.close()
            return body_text, content
        except Exception as e:
            browser.close()
            print(f"DEBUG: Browser Error: {e}")
            return "", ""

def llm_generate_solution(question_text):
    system_prompt = "You are a Python Data Analyst bot. Return ONLY valid Python code. Define variable 'result'."
    
    # 1. Find a working model dynamically
    model_name = get_working_model()
    print(f"DEBUG: Using model {model_name}")

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

def run_quiz_solver(start_url, email, secret):
    print(f"DEBUG: Starting solver for {start_url}", flush=True)
    
    current_url = start_url
    steps = 0
    while current_url and steps < 10:
        steps += 1
        print(f"--- Step {steps}: Processing {current_url} ---", flush=True)
        
        try:
            question_text, html_content = get_page_content(current_url)
            
            # --- ROBUST URL EXTRACTION ---
            submit_url = None
            match = re.search(r'(https?://[^\s"<>]+)', question_text)
            if match:
                submit_url = match.group(1)
            else:
                 match = re.search(r'(https?://[^\s"<>]+/submit)', html_content)
                 if match: submit_url = match.group(1)

            if submit_url:
                submit_url = submit_url.strip().strip(".").strip(",")

            print(f"DEBUG: Submit URL is {submit_url}")
            
            if not submit_url:
                print("DEBUG: No submit URL found. Stopping.")
                break

            # Generate Code
            code = llm_generate_solution(question_text)
            if not code:
                print("DEBUG: Failed to generate code. Skipping.")
                break
            
            print("DEBUG: Code generated. Executing...")
            
            # Execute Code
            answer = execute_generated_code(code)
            print(f"Calculated Answer: {answer}")

            if hasattr(answer, 'item'): answer = answer.item()
            
            payload = {"email": email, "secret": secret, "url": current_url, "answer": answer}
            
            print(f"DEBUG: Sending POST to {submit_url}")
            resp = requests.post(submit_url, json=payload, timeout=10)
            print(f"Server Response: {resp.json()}")
            
            data = resp.json()
            if data.get("correct") and "url" in data:
                current_url = data["url"]
            else:
                current_url = None
                
        except Exception as e:
            print(f"CRITICAL FAILURE: {traceback.format_exc()}", flush=True)
            break
