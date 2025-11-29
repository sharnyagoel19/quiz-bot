import requests
import os

# 1. YOUR RENDER URL (Make sure it has /solve at the end)
# I will use the one I saw in your logs, but check the prefix
# Use your actual Render URL here:
API_URL = "https://quiz-bot-solution1.onrender.com/solve" 

# 2. YOUR SECRET
MY_SECRET = "happysoul123" 

payload = {
    "email": "test_user@example.com",
    "secret": MY_SECRET,
    "url": "https://tds-llm-analysis.s-anand.net/demo"
}

print(f"🚀 Sending request to {API_URL}...")
try:
    response = requests.post(API_URL, json=payload, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        print("\n✅ SUCCESS! The server accepted the task.")
    else:
        print(f"\n❌ ERROR: Server replied with {response.status_code}")
except Exception as e:
    print(f"\n❌ CONNECTION FAILED: {e}")
