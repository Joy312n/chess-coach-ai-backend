from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import requests
import engine

# If you are using the database file we created earlier:
from database import save_game_and_update_profile, get_player_profile

app = FastAPI()

# Enable React to talk to Python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class RawPGNRequest(BaseModel):
    pgn: str
    username: str

class ReportRequest(BaseModel):
    analyzed_games: List[Dict[str, Any]]
    username: str

# --- ROUTES ---

@app.post("/upload-pgn/")
async def upload_pgn(file: UploadFile = File(...), username: str = Form(...)): 
    """Handles single file uploads from the UI"""
    content = await file.read()
    pgn_text = content.decode("utf-8")
    
    # 1. Run Stockfish Analysis
    analysis_result = engine.analyze_game_with_stockfish(pgn_text) 
    
    # 2. Save to Database (Optional: remove if not using MongoDB yet)
    try:
        await save_game_and_update_profile(username, analysis_result)
    except Exception as e:
        print(f"Database save skipped or failed: {e}")
    
    return {"filename": file.filename, "analysis": analysis_result}

@app.get("/fetch-games/{username}")
def fetch_games(username: str, limit: int = 10):
    """Fetches recent games from Chess.com with proper headers"""
    try:
        # Chess.com requires a User-Agent or they will 403 block you
        headers = {'User-Agent': 'ChessCoachApp/1.0 (Contact: your@email.com)'}
        archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
        response = requests.get(archives_url, headers=headers)
        
        if response.status_code != 200:
            return {"error": f"Chess.com returned error {response.status_code}"}
            
        archives = response.json().get("archives", [])
        if not archives:
            return {"error": "No game archives found for this user."}

        all_pgns = []
        # Reverse to get the most recent months first
        for archive_url in reversed(archives):
            games_data = requests.get(archive_url, headers=headers).json()
            # Reverse moves to get most recent games first
            for game in reversed(games_data.get("games", [])):
                if "pgn" in game:
                    all_pgns.append(game["pgn"])
                if len(all_pgns) >= limit:
                    break
            if len(all_pgns) >= limit:
                break

        return {"games_count": len(all_pgns), "pgns": all_pgns}
    except Exception as e:
        return {"error": str(e)}

@app.post("/analyze-raw-pgn/")
def analyze_raw_pgn(req: RawPGNRequest):
    """Bridge for the bulk analysis loop in React"""
    analysis = engine.analyze_game_with_stockfish(req.pgn)
    return {"analysis": analysis}

@app.post("/generate-report/")
def generate_report(req: ReportRequest):
    """The core Pattern Detector engine call"""
    report = engine.generate_profile_report(req.analyzed_games, req.username)
    return {"report": report}

@app.get("/profile/{username}")
async def get_profile(username: str):
    """Fetches historical stats from your local Database"""
    profile_data = await get_player_profile(username)
    if not profile_data:
        return {"message": "Profile not found."}
    return profile_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)