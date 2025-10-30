import os
import requests
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime
import pytz  # för svensk tid

# --- Ladda miljövariabler ---
load_dotenv(".env.local")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- Telegram ---
TELEGRAM_TOKEN = "8022888649:AAEzYijWiBhoeOgonFv2pSZacoXBlGcJWFw"
TELEGRAM_CHAT_ID = "7650344139"

# --- Initiera Supabase-klienten ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Svensk tidszon ---
sweden_tz = pytz.timezone("Europe/Stockholm")

def get_referee_stats(referee_name: str) -> pd.DataFrame:
    """
    Hämtar all statistik för en specifik domare (case-insensitive).
    """
    response = supabase.table("referee_stats").select("*").ilike("referee", referee_name).execute()
    if not response.data:
        print(f"Ingen data hittades för domare: {referee_name}")
        return pd.DataFrame()
    return pd.DataFrame(response.data)


def send_referee_to_telegram(df: pd.DataFrame, referee_name: str):
    """
    Skickar en snygg text med kaxig ton till Telegram med all statistik för domaren.
    """
    row = df.iloc[0]

    # --- Tid ---
    now = datetime.now(sweden_tz)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # --- Textmeddelande ---
    text = (
        f"🔥 *CornerDestroyerBot har snackat – här kommer reket!* 🔥\n\n"
        f"🏟️ *Liga:* {row['league']}\n"
        f"🧑‍⚖️ *Domare:* {row['referee']}\n"
        f"🟨 *Kort per match:* {row['avg_cards_per_match']}\n"
        f"📈 *Ligans snitt kort/match:* {row['league_avg_cards']}\n"
        f"📊 *Matcher dömda:* {row['matches_count']}\n\n"
        f"🚩 *Fouls per match:* {row['avg_fouls_per_match']}\n"
        f"⚖️ *Fouls per kort:* {row['fouls_per_card_ratio']}\n\n"
        f"🕒 *Rek-tid:* {timestamp}\n"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, data=data)
    r.raise_for_status()
    print(" Rek skickad till Telegram!")


if __name__ == "__main__":
    referee_name = "G ward"  # <-- byt till den du vill testa
    df = get_referee_stats(referee_name)
    if not df.empty:
        print(df.to_string(index=False))
        send_referee_to_telegram(df, referee_name)
    else:
        print("Ingen data hittades.")
