import chess.pgn
import chess.engine
import io
import requests # NEW: For fetching opening names

# ⚠️ IMPORTANT: Replace this string with the actual path to your Stockfish file
STOCKFISH_PATH = r"C:\Users\nitai\Desktop\chess-coach-ai\engine\stockfish\stockfish-windows-x86-64-avx2.exe"




# --- LOCAL OPENING DATABASE ---
LOCAL_OPENINGS = {
    "e4": ("B00", "King's Pawn Game"),
    "e4 e5": ("C20", "Open Game"),
    "e4 e5 Nf3": ("C40", "King's Knight Opening"),
    "e4 e5 Nf3 Nc6": ("C44", "King's Knight Opening"),
    "e4 e5 Nf3 Nc6 Bb5": ("C60", "Ruy Lopez"),
    "e4 e5 Nf3 Nc6 Bc4": ("C50", "Italian Game"),
    "e4 e5 Nf3 d5": ("C40", "Elephant Gambit"), 
    "e4 c5": ("B20", "Sicilian Defense"),
    "e4 c5 Nf3 d6 d4": ("B53", "Sicilian Defense: Open"),
    "e4 e6": ("C00", "French Defense"),
    "e4 c6": ("B10", "Caro-Kann Defense"),
    "d4": ("A40", "Queen's Pawn Game"),
    "d4 d5": ("D00", "Closed Game"),
    "d4 d5 c4": ("D06", "Queen's Gambit"),
    "d4 d5 c4 e6": ("D30", "Queen's Gambit Declined"),
    "d4 d5 c4 c6": ("D10", "Slav Defense"),
    "d4 d5 c4 c6 Nf3 Nf6 Nc3 e6": ("D43", "Semi-Slav Defense"), 
    "Nf3": ("A04", "Zukertort Opening"),
    "c4": ("A10", "English Opening")
}

def classify_move(cpl):
    if cpl is None: return "Book"
    if cpl <= 15: return "Best"
    if cpl <= 30: return "Excellent"
    if cpl <= 60: return "Good"
    if cpl <= 100: return "Inaccuracy"
    if cpl <= 250: return "Mistake"
    return "Blunder"

def detect_motif(board, move, info_before, info_after):
    """Detects why a move was a blunder or what was missed."""
    # Check for Hanging Pieces
    target_sq = move.to_square
    piece = board.piece_at(target_sq)
    if piece:
        color = piece.color
        if len(board.attackers(not color, target_sq)) > 0 and len(board.attackers(color, target_sq)) == 0:
            return "Hanging Piece"

    # Check for Mates
    score_before = info_before["score"].white().score(mate_score=10000) if "score" in info_before else 0
    score_after = info_after["score"].white().score(mate_score=10000) if "score" in info_after else 0
    
    if score_before is not None and score_after is not None:
        if abs(score_before) < 800 and abs(score_after) > 800:
            if info_after["score"].white().is_mate():
                return "Mate Threat"
        
        # Major Tactical Swing (Forks, Pins, etc.)
        if abs(score_before - score_after) > 500:
            return "Major Tactical Blunder"
    
    return "Positional Error"

def get_opening_info(game):
    moves = []
    board = game.board()
    for i, move in enumerate(game.mainline_moves()):
        if i >= 10: break
        moves.append(board.san(move))
        board.push(move)
        
    while len(moves) > 0:
        play_string = " ".join(moves)
        if play_string in LOCAL_OPENINGS:
            eco_code, op_name = LOCAL_OPENINGS[play_string]
            return op_name, eco_code
        moves.pop() 
        
    return None, None

def analyze_game_with_stockfish(pgn_string: str):
    pgn_io = io.StringIO(pgn_string)
    game = chess.pgn.read_game(pgn_io)
    if game is None: return {"error": "Could not parse PGN"}

    board = game.board()
    move_data = []
    
    try: engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    except FileNotFoundError: return {"error": "Stockfish not found. Check the path."}

    info_before = engine.analyse(board, chess.engine.Limit(time=0.1))

    for move in game.mainline_moves():
        is_white_move = board.turn
        fen_before = board.fen() 
        
        best_line_uci = [m.uci() for m in info_before.get("pv", [])[:1]]
        prev_score_obj = info_before["score"].white()
        prev_score = prev_score_obj.score(mate_score=10000)

        board.push(move)
        
        info_after = engine.analyse(board, chess.engine.Limit(time=0.1))
        current_score_obj = info_after["score"].white()
        current_score = current_score_obj.score(mate_score=10000)
        
        if prev_score is not None and current_score is not None:
            cpl = (prev_score - current_score) if is_white_move else (current_score - prev_score)
        else:
            cpl = 0

        move_class = classify_move(cpl)
        mistake_tag = None
        punishment_line_uci = []
        
        if cpl > 100: 
            mistake_tag = detect_motif(board, move, info_before, info_after)
            punishment_line_uci = [m.uci() for m in info_after.get("pv", [])[:5]]

        move_data.append({
            "move": move.uci(),
            "played_by": "White" if is_white_move else "Black",
            "score": current_score,
            "cpl": cpl,
            "classification": move_class,
            "tag": mistake_tag,
            "fen_before": fen_before,
            "fen": board.fen(),
            "best_line": best_line_uci,
            "punishment_line": punishment_line_uci
        })
        info_before = info_after

    engine.quit()
    
    headers = dict(game.headers)
    if "Opening" not in headers:
        opening_name, eco_code = get_opening_info(game)
        if opening_name:
            headers["Opening"] = opening_name
            if eco_code:
                headers["ECO"] = eco_code

    return {
        "headers": headers,
        "total_moves": len(move_data),
        "analysis_by_move": move_data,
        "final_fen": board.fen()
    }

def generate_profile_report(analyzed_games, username):
    report = {
        "total_games": len(analyzed_games),
        "wins": 0, "losses": 0, "draws": 0,
        "blown_leads": 0,
        "blunders_by_phase": {"Opening": 0, "Middlegame": 0, "Endgame": 0},
        "insights": [],
        "action_plan": [],
        "openings_as_white": {},
        "openings_as_black": {}
    }

    motif_stats = {"Missed": {}, "Fell For": {}}
    examples_by_phase = {"Opening": [], "Middlegame": [], "Endgame": []}

    for g_idx, game in enumerate(analyzed_games):
        headers = game.get("headers", {})
        user_color = "White" if headers.get("White", "").lower() == username.lower() else "Black"
        result = headers.get("Result", "*")
        opponent = headers.get("Black", "Unknown") if user_color == "White" else headers.get("White", "Unknown")
        
        # 1. Result Tracking
        won = (user_color == "White" and result == "1-0") or (user_color == "Black" and result == "0-1")
        if won: report["wins"] += 1
        elif result == "1/2-1/2": report["draws"] += 1
        else: report["losses"] += 1

        # 2. Opening Context
        op = headers.get("Opening", "Unknown Opening")
        target_dict = report["openings_as_white"] if user_color == "White" else report["openings_as_black"]
        if op not in target_dict:
            target_dict[op] = {"played": 0, "wins": 0, "early_errors": 0, "examples": []}
        target_dict[op]["played"] += 1
        if won: target_dict[op]["wins"] += 1

        # 3. Move Analysis
        for i, m in enumerate(game.get("analysis_by_move", [])):
            if m["played_by"] == user_color:
                move_num = (i // 2) + 1
                phase = "Opening" if move_num <= 10 else "Middlegame" if move_num <= 30 else "Endgame"
                
                if m["classification"] in ["Mistake", "Blunder"]:
                    report["blunders_by_phase"][phase] += 1
                    motif = m.get("tag", "Tactical Oversight")
                    
                    ex = {
                        "fen": m["fen_before"], "move": m["move"], "opponent": opponent,
                        "move_number": move_num, "game_index": g_idx, "move_index": i,
                        "classification": m["classification"], "punishment_line": m.get("punishment_line", [])
                    }
                    
                    # Track "Fell For" (Defensive)
                    if motif not in motif_stats["Fell For"]: motif_stats["Fell For"][motif] = []
                    motif_stats["Fell For"][motif].append(ex)
                    examples_by_phase[phase].append(ex)

                    if phase == "Opening":
                        target_dict[op]["early_errors"] += 1
                        target_dict[op]["examples"].append(ex)

    # --- Insight Generation ---

    # A. Phase Analysis
    for phase, count in report["blunders_by_phase"].items():
        if count > 0:
            report["insights"].append({
                "title": f"Phase Study: {phase}",
                "description": f"You struggle in the {phase} with {count} major blunders. This is your high-priority area.",
                "examples": examples_by_phase[phase]
            })
            if phase == "Endgame":
                report["action_plan"].append("Study King & Pawn endgames. You're losing drawn positions late in the game.")
            elif phase == "Middlegame":
                report["action_plan"].append("Improve Middlegame planning. Before moving, check if your target square is defended.")

    # B. Motif Analysis (Tactical Habits)
    for motif, exs in motif_stats["Fell For"].items():
        report["insights"].append({
            "title": f"Defensive Flaw: {motif}",
            "description": f"You're vulnerable to {motif}s. You've fallen for this {len(exs)} times recently.",
            "examples": exs
        })
        report["action_plan"].append(f"Solve 15 puzzles on '{motif}' to stop making this mistake.")

    # C. Opening Analysis (White & Black)
    for color, d in [("White", report["openings_as_white"]), ("Black", report["openings_as_black"])]:
        for op, stats in d.items():
            if stats["played"] > 0:
                win_pct = (stats["wins"]/stats["played"])*100
                if win_pct < 45 or stats["early_errors"] > 0:
                    report["insights"].append({
                        "title": f"Opening Gap: {op} ({color})",
                        "description": f"Win Rate: {win_pct:.0f}%. You average {stats['early_errors']} blunders in the first 10 moves.",
                        "examples": stats["examples"]
                    })
                    report["action_plan"].append(f"Refresh your '{op}' knowledge. You're blundering theory early.")

    return report