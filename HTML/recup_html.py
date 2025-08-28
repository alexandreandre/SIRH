import requests
from bs4 import BeautifulSoup
import os

url = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"   
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/119.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers, timeout=10)
response.raise_for_status()

html = response.text
soup = BeautifulSoup(html, "html.parser")

# nom du fichier dans le même dossier que ton script
output_file = os.path.join(os.path.dirname(__file__), "page.html")

with open(output_file, "w", encoding="utf-8") as f:
    f.write(soup.prettify())

print(f"HTML enregistré dans {output_file}")
