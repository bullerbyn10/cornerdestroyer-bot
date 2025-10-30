import requests

# ============= CONFIG =============
COMP_ID = 1          # Premier League
COMP_SEASON_ID = 777 # 2025/26 enligt din lista
PAGE_SIZE = 40
# =================================

HEADERS = {
    "Origin": "https://www.premierleague.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

def get_fixtures(comp_id: int, comp_season_id: int, page_size: int = 40):
    """Hämtar alla matcher (fixture-lista)"""
    url = f"https://footballapi.pulselive.com/football/fixtures?comps={comp_id}&compSeasons={comp_season_id}&page=0&pageSize={page_size}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    return data.get("content", [])

def get_referee(match_id) -> str | None:
    """Hämtar domarnamn för en specifik match"""
    match_id = int(match_id)
    url = f"https://footballapi.pulselive.com/football/fixtures/{match_id}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    data = r.json()

    officials = data.get("matchOfficials", [])
    if not officials:
        return None

    # 🧩 Ny, säkrare hantering
    for official in officials:
        # säkra typkollen först
        if isinstance(official, dict):
            role = official.get("role") or {}
            if isinstance(role, dict) and role.get("name") == "Referee":
                return official.get("name")
        elif isinstance(official, str):
            if "Referee" in official:
                parts = official.split(":")
                if len(parts) > 1:
                    return parts[1].strip()

    return None



if __name__ == "__main__":
    print(f" Hämtar matcher för Premier League {COMP_SEASON_ID}...\n")
    fixtures = get_fixtures(COMP_ID, COMP_SEASON_ID, PAGE_SIZE)
    if not fixtures:
        print(" Inga matcher hittades (kan vara att säsongen inte startat ännu).")
    else:
        for f in fixtures:
            match_id = f["id"]
            home = f["teams"][0]["team"]["name"]
            away = f["teams"][1]["team"]["name"]
            status = f["status"]
            referee = get_referee(match_id)
            print(f"{home} vs {away} {referee or 'Okänd'} ({status})")
