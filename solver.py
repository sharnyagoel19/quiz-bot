import os
import sys
import re
import json
import requests
import traceback
import time

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
    Priority List:
    1. Gemini 1.5 Flash (Best for Free Tier)
    2. Gemini Pro (Backup)
    """
    try:
        print("DEBUG: Checking available models...")
        available_models = list(genai.list_models())
        
        # 1. Look specifically for the standard FLASH model first
        for m in available_models:
            if 'gemini-1.5-flash' in m.name and 'latest' not in m.name:
                print(f"DEBUG: Selected Priority Model: {m.name}")
                return m.name
        
        # 2. Look for ANY Flash model
        for m in available_models:
            if 'flash' in m.name and 'generateContent' in m.supported_generation_methods:
                print(f"DEBUG: Selected Fallback Flash: {m.name}")
                return m.name

        # 3. Last Resort: Pro
        for m in available_models:
             if 'gemini-1.5-pro' in m.name:
                return m.name
                
    except Exception as e:
        print(f"DEBUG: Could not list models: {e}")
    
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
    # UPDATED PROMPT: Explicitly warn against returning objects
    system_prompt = """
    You are a Python Data Analyst bot. 
    1. Write a Python script to solve the problem.
    2. Define a variable 'result' with the final answer.
    3. 'result' MUST be a string, integer, or boolean.
    4. 'result' CANNOT be a Response object or a DataFrame.
    5. If downloading a file, 'result' should be the extracted content, not the request object.
    Return ONLY valid Python code.
    """
    
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

def sanitize_answer(answer):
    """
    Ensures the answer is JSON serializable.
    Converts Response objects, Numpy types, etc. into strings/ints.
    """
    try:
        # If it's a Request Response object (the specific error you had)
        if hasattr(answer, 'text') and hasattr(answer, 'status_code'):
            return answer.text
        
        # If it's a Numpy number (common in data analysis)
        if hasattr(answer, 'item'):
            return answer.item()
            
        # If it's a Pandas DataFrame/Series
        if hasattr(answer, 'to_dict'):
            return str(answer)
            
        return answer
    except Exception as e:
        return str(answer)

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
            raw_answer = execute_generated_code(code)
            print(f"DEBUG: Raw Answer Type: {type(raw_answer)}")
            
            # --- NEW: SANITIZE ANSWER ---
            answer = sanitize_answer(raw_answer)
            print(f"Calculated Answer (Sanitized): {answer}")
            
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
