# etl/adapters/incois_pfz_scraper.py
"""
INCOIS PFZ scraper (heuristic).
This scrapes INCOIS PFZ advisory page to extract advisory text blocks.
Use responsibly and check INCOIS terms of use.
"""
import requests
from bs4 import BeautifulSoup
import re
import logging
from etl.qc_provenance import make_provenance

logger = logging.getLogger("incois_pfz_scraper")
INCOIS_PFZ_URL = "https://incois.gov.in/MarineFisheries/PfzAdvisory"

def fetch_pfzs():
    try:
        r = requests.get(INCOIS_PFZ_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")
        blocks = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.search(r"PFZ|Potential Fishing Zone|Potential Fish|PFZ Advisory", line, re.I):
                blocks.append(line)
        prov = make_provenance("INCOIS_PFZ", INCOIS_PFZ_URL)
        return {"raw": "\n".join(blocks), "provenance": prov}
    except Exception as e:
        logger.exception("INCOIS PFZ fetch failed: %s", e)
        return {"raw": "", "provenance": make_provenance("INCOIS_PFZ", INCOIS_PFZ_URL)}

