from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

def get_referee_selenium(match_url: str) -> str | None:
    """Laddar Sofascore-sidan och hämtar domarens namn även om det ligger i en <div> efter Referee."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(match_url)
        time.sleep(4)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        page_text = driver.page_source

        # ny regex som tillåter div och span efter "Referee"
        match = re.search(
            r"Referee(?:.|\n){0,300}?<span[^>]*>\s*<div[^>]*>\s*<span[^>]*>([A-ZÅÄÖÉÈa-zåäöéè\s'\-]+)</span>",
            page_text,
            re.IGNORECASE
        )

        if match:
            referee = match.group(1).strip()
            print(f" Domare: {referee}")
            return referee

        # annars visa utdrag så vi kan felsöka vidare
        snippet = page_text[page_text.find("Referee"):page_text.find("Referee")+400]
        print(" Kunde inte hitta domarens namn – textutdrag:")
        print(snippet)
        return None

    except Exception as e:
        print(f" Fel i Selenium: {e}")
        return None
    finally:
        driver.quit()


if __name__ == "__main__":
    match_url = "https://www.sofascore.com/football/match/leeds-united-brighton-and-hove-albion/FsJ#id:14025273"
    get_referee_selenium(match_url)
