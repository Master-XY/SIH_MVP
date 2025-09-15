# etl/adapters/incois_pfz_scraper.py
import requests, re, logging
from bs4 import BeautifulSoup
from etl.qc_provenance import make_provenance

INCOIS_PFZ_URL = "https://incois.gov.in/MarineFisheries/PfzAdvisory"

def fetch_pfzs():
    r = requests.get(INCOIS_PFZ_URL, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # Heuristic: find text containing "PFZ" or "Potential Fishing Zone"
    text = soup.get_text(separator="\n")
    blocks = []
    for line in text.splitlines():
        if re.search(r"PFZ|Potential Fishing Zone|Potential Fish", line, re.I):
            blocks.append(line.strip())
    prov = make_provenance("INCOIS_PFZ", INCOIS_PFZ_URL)
    return {"raw": "\n".join(blocks), "provenance": prov}
