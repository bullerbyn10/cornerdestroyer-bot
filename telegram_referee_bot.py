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

# --- .env ---
from dotenv import load_dotenv

# =========================
# Konfiguration
# =========================
load_dotenv(".env.local")  # innehåller SUPABASE_URL, SUPABASE_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")   or "8022888649:REPLACE_ME"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "7650344139"

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://xxxxx.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "sbp_XXXX"

### NY SUPABASE-DEL ###
def supabase_get_ref_row(initial_last: str) -> Optional[dict]:
    """
    Hämtar en rad ur referee_stats via Supabase REST API (ingen SDK).
    Matchar t.ex. 'M Oliver' (case-insensitive).
    """
    url = f"{SUPABASE_URL}/rest/v1/referee_stats"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    params = {
        "select": "*",
        "referee": f"ilike.{initial_last}",
        "limit": 1,
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None
    except Exception as e:
        print("Supabase REST error:", e)
        return None
### SLUT NY SUPABASE-DEL ###

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
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# =========================
# Sofascore: hitta match-URL från fri text
# =========================
def resolve_sofascore_url_from_query(query: str) -> Optional[str]:
    driver = make_driver()
    try:
        driver.get("https://www.sofascore.com/")
        time.sleep(3)
        search_btns = driver.find_elements(By.XPATH, "//*[@aria-label='Search' or @data-testid='search']")
        if search_btns:
            search_btns[0].click()
            time.sleep(1.5)
        inputs = driver.find_elements(By.XPATH, "//input[@type='search' or @placeholder='Search']")
        if not inputs:
            return None
        box = inputs[0]
        box.clear()
        box.send_keys(query)
        time.sleep(2.5)
        links = driver.find_elements(By.XPATH, "//a[contains(@href,'/football/match/')]")
        if not links:
            return None
        return links[0].get_attribute("href")
    except Exception as e:
        print("resolve_sofascore_url_from_query error:", e)
        return None
    finally:
        driver.quit()

# =========================
# Sofascore: hämta domare från matchsida
# =========================
def get_referee_from_sofascore(match_url: str) -> Optional[str]:
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
# Telegram-pollning & hantering
# =========================
def get_updates(offset: Optional[int] = None) -> list[dict]:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 25}
    if offset:
        params["offset"] = offset
    r = requests.get(url, params=params, timeout=35)
    r.raise_for_status()
    return r.json().get("result", [])

def handle_message(text: str):
    text = text.strip()
    sofascore_url = None
    m = re.search(r"https?://www\.sofascore\.com/[^\s]+", text)
    if m:
        sofascore_url = m.group(0)
    if not sofascore_url:
        sofascore_url = resolve_sofascore_url_from_query(text)
    if not sofascore_url:
        send_telegram_text("❌ Hittade ingen match på Sofascore för din förfrågan.")
        return
    referee_full = get_referee_from_sofascore(sofascore_url)
    if not referee_full:
        send_telegram_text("❌ Hittade ingen domare på matchsidan (kan vara ej publicerad).")
        return

    key = format_ref_name_for_supabase(referee_full)
    ref_row = supabase_get_ref_row(key)

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
# Main loop
# =========================
def run_bot():
    send_telegram_text("🤖 CornerDestroyerBot är online. Skicka en Sofascore-länk eller skriv ett lagmöte.")
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
