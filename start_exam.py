import requests

# 1. YOUR RENDER URL (Keep the /solve at the end)
# Example: "https://quiz-bot-solution1.onrender.com/solve"
API_URL = "https://quiz-bot-solution1.onrender.com/solve" 

# 2. YOUR SECRET
MY_SECRET = "happysoul123" 

# 3. THE EXAM STARTING URL (From your snippet)
PROJECT_URL = "https://tds-llm-analysis.s-anand.net/project2"

payload = {
    "email": "your_email@example.com", # Use your actual student email
    "secret": MY_SECRET,
    "url": PROJECT_URL
}

print(f"🚀 Triggering Exam at {API_URL}...")
try:
    # We set a short timeout because your server returns 200 OK immediately
    # while it solves in the background.
    response = requests.post(API_URL, json=payload, timeout=10)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        print("\n✅ SUCCESS! Your bot has started the exam.")
        print("👀 GO TO RENDER LOGS NOW to watch it solve Step 1.")
    else:
        print(f"\n❌ ERROR: Server replied with {response.status_code}")
except Exception as e:
    print(f"\n❌ CONNECTION FAILED: {e}")