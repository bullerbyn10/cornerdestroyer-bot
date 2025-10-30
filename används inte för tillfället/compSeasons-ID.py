import requests

headers = {
    "Origin": "https://www.premierleague.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

url = "https://footballapi.pulselive.com/football/competitions/1/compseasons"
r = requests.get(url, headers=headers)
r.raise_for_status()
data = r.json()

# Hantera båda typer av svar
comp_seasons = data.get("compSeasons") or data.get("content") or []

if not comp_seasons:
    print(" Hittade inga compSeasons i svaret:")
    print(data)
else:
    print("Premier League säsonger:\n")
    for season in comp_seasons:
        label = season.get("label")
        comp_id = season.get("id")
        print(f"{label}: {comp_id}")
