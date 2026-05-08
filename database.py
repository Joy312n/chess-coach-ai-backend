# backend/database.py
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

# Connect to MongoDB (Default local connection)
MONGO_DETAILS = "mongodb+srv://kngjoy:032005@cluster0.3zixssm.mongodb.net/Player-Profie?retryWrites=true&w=majority&appName=Cluster0"
client = AsyncIOMotorClient(MONGO_DETAILS)
db = client.chess_coach

# Collections
games_collection = db.get_collection("games")
profiles_collection = db.get_collection("profiles")

async def save_game_and_update_profile(username: str, analysis_data: dict):
    """Saves the game blunders and updates the user's weakness profile."""
    
    # 1. Extract only the bad moves to save space
    blunders = [m for m in analysis_data["analysis_by_move"] if m["cpl"] > 200]
    
    # 2. Save the game record
    game_record = {
        "username": username,
        "white": analysis_data["headers"].get("White", "Unknown"),
        "black": analysis_data["headers"].get("Black", "Unknown"),
        "date_analyzed": datetime.utcnow(),
        "blunders_count": len(blunders),
        "blunders": blunders
    }
    await games_collection.insert_one(game_record)

    # 3. Update the Player Profile (The "Coach" Brain)
    # We count how many times they make specific types of mistakes
    motif_counts = {}
    for blunder in blunders:
        # Only count blunders made by the target user
        if blunder["played_by"] == "White" and analysis_data["headers"].get("White") == username:
            tag = blunder.get("tag", "Unknown")
            motif_counts[tag] = motif_counts.get(tag, 0) + 1
            
        elif blunder["played_by"] == "Black" and analysis_data["headers"].get("Black") == username:
            tag = blunder.get("tag", "Unknown")
            motif_counts[tag] = motif_counts.get(tag, 0) + 1

    # Push the new stats into their MongoDB profile
    if motif_counts:
        # Using $inc to add these new mistakes to their all-time totals
        inc_data = {f"weaknesses.{motif}": count for motif, count in motif_counts.items()}
        inc_data["total_blunders_analyzed"] = len(blunders)
        
        await profiles_collection.update_one(
            {"username": username},
            {"$inc": inc_data},
            upsert=True # Creates the profile if it doesn't exist yet
        )
        
    return True

async def get_player_profile(username: str):
    """Fetches the aggregated weakness data for the frontend dashboard."""
    profile = await profiles_collection.find_one({"username": username})
    if profile:
        profile["_id"] = str(profile["_id"]) # Convert ObjectId to string for JSON
    return profile