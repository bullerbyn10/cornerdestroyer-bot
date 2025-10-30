import os
import time
import re
import requests
from dataclasses import dataclass
from typing import Optional
import sys

sys.stdout.reconfigure(encoding="utf-8")

# --- Selenium (för Sofascore-sök + domare) ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# --- Supabase ---
from supabase import create_client
from dotenv import load_dotenv

# =========================
# Konfiguration
# =========================
load_dotenv(".env.local")  # innehåller SUPABASE_URL, SUPABASE_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")   or "8022888649:REPLACE_ME"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "7650344139"

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://xxxxx.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "sbp_XXXX"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# Hjälpare
# =========================
def format_ref_name_for_supabase(fullname: str) -> str:
    """
    Gör om 'Michael Oliver' -> 'M Oliver' för att matcha din tabell.
    Behåller accenter och apostrof/streck.
    """
    name = fullname.strip()
    parts = [p for p in re.split(r"\s+", name) if p]
    if len(parts) >= 2:
        initial = parts[0][0]
        last = parts[-1]
        return f"{initial} {last}"
    return name

def send_telegram_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()

# =========================
# Selenium: init & teardown
# =========================
def make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    # Om du vill köra med Edge istället (om Chrome saknas):
    # options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# =========================
# Sofascore: hitta match-URL från fri text
# =========================
def resolve_sofascore_url_from_query(query: str) -> Optional[str]:
    """
    Öppnar sofascore.com, använder sidans sök för att hitta en match för given query.
    Returnerar URL till matchsidan, eller None.
    """
    driver = make_driver()
    try:
        driver.get("https://www.sofascore.com/")
        time.sleep(3)

        # Öppna sök (klicka på sök-ikon)
        # Sökmotorn kan ändras – denna funkar i skrivande stund:
        # Leta efter knappen med aria-label 'Search' eller ikon i headern
        search_btns = driver.find_elements(By.XPATH, "//*[@aria-label='Search' or @data-testid='search']")
        if not search_btns:
            # fallback: prova hitta ett input direkt
            pass
        else:
            search_btns[0].click()
            time.sleep(1.5)

        # Sökfält (är ofta ett <input> i en popover)
        inputs = driver.find_elements(By.XPATH, "//input[@type='search' or @placeholder='Search']")
        if not inputs:
            # sista fallback: försök direkt URL med query (client-render kan ändå svara)
            # Funkar ofta: /search, men om inte, returnera None
            return None

        box = inputs[0]
        box.clear()
        box.send_keys(query)
        time.sleep(2.5)  # vänta på autosuggest

        # Hitta första “Matches”-resultat (för Football)
        # Vi letar efter en länk som innehåller '/football/match/' i href
        links = driver.find_elements(By.XPATH, "//a[contains(@href,'/football/match/')]")
        if not links:
            return None

        match_href = links[0].get_attribute("href")
        return match_href
    except Exception as e:
        print("resolve_sofascore_url_from_query error:", e)
        return None
    finally:
        driver.quit()

# =========================
# Sofascore: hämta domare från matchsida
# =========================
def get_referee_from_sofascore(match_url: str) -> Optional[str]:
    """
    Laddar Sofascore-matchsidan och plockar domare via robust regex mot HTML.
    Fungerar för strukturen:
    Referee</span><span ...><div ...><span ...>Luca Pairetto</span>
    """
    driver = make_driver()
    try:
        driver.get(match_url)
        time.sleep(4)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.5)

        page = driver.page_source
        m = re.search(
            r"Referee(?:.|\n){0,300}?<span[^>]*>\s*<div[^>]*>\s*<span[^>]*>([A-ZÅÄÖÉÈa-zåäöéè\s'\-]+)</span>",
            page,
            re.IGNORECASE
        )
        if m:
            return m.group(1).strip()
        return None
    except Exception as e:
        print("get_referee_from_sofascore error:", e)
        return None
    finally:
        driver.quit()

# =========================
# Supabase: hämta rad för domare
# =========================
def supabase_get_ref_row(initial_last: str) -> Optional[dict]:
    """
    Slår på referee_stats med 'M Oliver'-stil (case-insensitive).
    Returnerar första träffen eller None.
    """
    try:
        res = supabase.table("referee_stats").select("*").ilike("referee", initial_last).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        print("Supabase error:", e)
        return None

# =========================
# Parsning av inkommande Telegram-meddelanden
# =========================
def get_updates(offset: Optional[int] = None) -> list[dict]:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 25}
    if offset:
        params["offset"] = offset
    r = requests.get(url, params=params, timeout=35)
    r.raise_for_status()
    data = r.json()
    return data.get("result", [])

def handle_message(text: str):
    """
    Huvudlogik när du skriver t.ex.:
      - "brighton leeds"
      - en Sofascore-länk
    """
    text = text.strip()

    # 1) Om texten redan är en Sofascore-länk, använd den
    sofascore_url = None
    m = re.search(r"https?://www\.sofascore\.com/[^\s]+", text)
    if m:
        sofascore_url = m.group(0)

    # 2) Annars försök hitta en match-URL via sök
    if not sofascore_url:
        sofascore_url = resolve_sofascore_url_from_query(text)

    if not sofascore_url:
        send_telegram_text("❌ Hittade ingen match på Sofascore för din förfrågan.")
        return

    # 3) Hämta domare via Selenium-scrape
    referee_full = get_referee_from_sofascore(sofascore_url)
    if not referee_full:
        send_telegram_text("❌ Hittade ingen domare på matchsidan (kan vara ej publicerad).")
        return

    # 4) Mappa till Supabase-format ("M Oliver") och hämta rad
    key = format_ref_name_for_supabase(referee_full)
    ref_row = supabase_get_ref_row(key)

    # 5) Skicka svar
    if not ref_row:
        send_telegram_text(
            f"🧑‍⚖️ Domare: *{referee_full}*\n"
            f"(kunde inte hitta `{key}` i Supabase – kontrollera stavning/ligan.)"
        )
        return

    msg = (
        f"🔥 *CornerDestroyerBot har snackat – här kommer reket!* 🔥\n"
        f"🏟️ Liga: {ref_row.get('league','N/A')}\n\n"

        f"🧑‍⚖️ *Domare:* {referee_full}\n"
        f"📊 Matcher dömda: {ref_row.get('matches_count','N/A')}\n"
        f"🟨 Kort/match: {ref_row.get('avg_cards_per_match','N/A')}\n"
        f"📈 Ligasnitt kort/match: {ref_row.get('league_avg_cards','N/A')}\n\n"

        f"🚩 Fouls/match: {ref_row.get('avg_fouls_per_match','N/A')}\n"
        f"⚖️ Fouls/kort: {ref_row.get('fouls_per_card_ratio','N/A')}\n"
        
    )
    send_telegram_text(msg)

# =========================
# Main loop (long polling)
# =========================
def run_bot():
    send_telegram_text("🤖 CornerDestroyerBot är online. skicka en Sofascore-länk på den match som du vill reka.")
    update_offset = None
    while True:
        try:
            updates = get_updates(update_offset)
            for u in updates:
                update_offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                if str(chat_id) != str(TELEGRAM_CHAT_ID):
                    # valfritt: ignorera andra chattar än din egen
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                handle_message(text)
        except Exception as e:
            print("Loop error:", e)
            time.sleep(2)

if __name__ == "__main__":
    run_bot()
