import os
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
# Import the function from solver.py
from solver import run_quiz_solver

app = FastAPI()

# --- CONFIGURATION ---
# These are loaded from Render Environment Variables
MY_EMAIL = os.getenv("MY_EMAIL", "default_email@example.com")
MY_SECRET = os.getenv("MY_SECRET", "default_secret")

class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str

@app.get("/")
def home():
    return {"status": "Active", "endpoints": "/solve"}

@app.post("/solve")
async def solve_endpoint(payload: QuizRequest, background_tasks: BackgroundTasks):
    """
    1. Verify Secret.
    2. Return 200 OK immediately.
    3. Run the heavy solving logic in the background.
    """
    print(f"Received request for URL: {payload.url}")
    
    # 1. Security Check
    if payload.secret != MY_SECRET:
        print(f"Unauthorized access attempt. Expected {MY_SECRET}, got {payload.secret}")
        raise HTTPException(status_code=403, detail="Invalid Secret")

    # 2. Start the solver in the background
    # This ensures we respond within seconds, even if the quiz takes minutes.
    background_tasks.add_task(run_quiz_solver, payload.url, MY_EMAIL, MY_SECRET)
    
    return {"message": "Task accepted. Solver started."}
