import time
import os  # <-- On importe le module "os" pour gérer les dossiers
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration de Selenium (inchangée) ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# --- Logique de scraping (inchangée) ---
url = "https://www.legisocial.fr/reperes-sociaux/indemnites-journalieres-de-securite-sociale-ijss-2025.html"

print("Chargement de la page avec Selenium...")
driver.get(url)
time.sleep(5)
html = driver.page_source
print("Page chargée avec succès !")
driver.quit()

# --- Parsing et Enregistrement dans le dossier "HTML" ---
soup = BeautifulSoup(html, "html.parser")

# 1. Définir le nom du dossier
output_dir = "HTML"

# 2. Créer le dossier s'il n'existe pas déjà
os.makedirs(output_dir, exist_ok=True)

# 3. Construire le chemin complet vers le fichier
# os.path.join() assemble correctement le chemin ("HTML/page_agirc-arrco.html")
file_name = "page2.html"
output_file_path = os.path.join(output_dir, file_name)

# 4. Enregistrer le fichier à cet emplacement
with open(output_file_path, "w", encoding="utf-8") as f:
    f.write(soup.prettify())

print(f"✅ HTML enregistré avec succès dans : {output_file_path}")