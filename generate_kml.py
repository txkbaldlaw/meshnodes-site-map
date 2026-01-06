#!/usr/bin/env python3
import csv
import html
import os
import sys
import urllib.request
from datetime import datetime, timezone

# ---- Configuration ----
DATASET_NAME = "FLG/TwiceAsNice MeshCore Site Map"

CSV_URL = os.environ.get("SHEET_CSV_URL", "").strip()
OUTPUT_KML = "sites.kml"
OUTPUT_NETWORKLINK = "networklink.kml"

# This should be the *public* URL to sites.kml on GitHub Pages after deployment
DATASET_URL = os.environ.get("DATASET_URL", "").strip()

# 10 minutes = 600 seconds
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "600"))

# Category -> KML colors in AABBGGRR (alpha, blue, green, red)
CATEGORY_COLORS = {
    "Owner Approved": "ff90ee90",     # Light Green
    "Group Approved": "ffe6add8",     # Lavender
    "Node Installed": "ff006400",     # Dark Green
    "Suggested": "ffadd8e6",          # Light Blue
    "Owner Requested": "ff00a5ff",    # Orange
    "Owner Rejected": "ff0000ff",     # Red
    "Group Rejected": "ff000000",     # Black
}

REQUIRED_COLUMNS = [
    "Name",
    "Street Address",
    "Latitude",
    "Longitude",
    "Category",
    "Notes",
    "Installed Node Name",
]

def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_csv(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8", errors="replace")

def build_styles() -> str:
    out = []
    for cat, color in CATEGORY_COLORS.items():
        out.append(f"""
    <Style id="{html.escape(cat)}">
      <IconStyle>
        <color>{color}</color>
        <scale>1.1</scale>
      </IconStyle>
      <LabelStyle>
        <scale>0.9</scale>
      </LabelStyle>
    </Style>""")
    return "\n".join(out)

def safe_float(x):
    if x is None:
        return None
    x = str(x).strip()
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None

def main() -> None:
    if not CSV_URL:
        die("SHEET_CSV_URL env var is required (your published CSV link).")

    csv_text = fetch_csv(CSV_URL)
    reader = csv.DictReader(csv_text.splitlines())

    cols = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        die(f"Missing columns in CSV: {missing}. Found: {cols}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    placemarks = []
    bad_rows = 0

    for i, row in enumerate(reader, start=2):
        name = (row.get("Name") or "").strip()
        address = (row.get("Street Address") or "").strip()
        category = (row.get("Category") or "").strip()
        notes = (row.get("Notes") or "").strip()
        installed_node = (row.get("Installed Node Name") or "").strip()

        lat = safe_float(row.get("Latitude"))
        lon = safe_float(row.get("Longitude"))

        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            bad_rows += 1
            continue

        style_url = f"#{category}" if category in CATEGORY_COLORS else ""

        desc = (
            f"<b>Address:</b> {html.escape(address)}<br/>"
            f"<b>Status:</b> {html.escape(category)}<br/>"
            f"<b>Notes:</b> {html.escape(notes)}<br/>"
            f"<b>Installed Node:</b> {html.escape(installed_node)}<br/>"
            f"<i>Updated (UTC):</i> {now}<br/>"
            f"<i>Refresh:</i> every {REFRESH_SECONDS // 60} minutes"
        )

        placemarks.append(f"""
    <Placemark>
      <name>{html.escape(name or address or f"Row {i}")}</name>
      {"<styleUrl>"+html.escape(style_url)+"</styleUrl>" if style_url else ""}
      <description><![CDATA[{desc}]]></description>
      <Point>
        <coordinates>{lon},{lat}</coordinates>
      </Point>
    </Placemark>""")

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{html.escape(DATASET_NAME)}</name>
    <description><![CDATA[
      Live dataset generated from Google Sheets.<br/>
      Updated (UTC): {now}<br/>
      Rows skipped (missing/invalid lat/lon): {bad_rows}
    ]]></description>
{build_styles()}
{''.join(placemarks)}
  </Document>
</kml>
"""

    with open(OUTPUT_KML, "w", encoding="utf-8") as f:
        f.write(kml)

    dataset_href = DATASET_URL if DATASET_URL else "https://txkbaldlaw.github.io/meshnodes-site-map/sites.kml"

    networklink = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <NetworkLink>
    <name>{html.escape(DATASET_NAME)}</name>
    <Link>
      <href>{html.escape(dataset_href)}</href>
      <refreshMode>onInterval</refreshMode>
      <refreshInterval>{REFRESH_SECONDS}</refreshInterval>
    </Link>
  </NetworkLink>
</kml>
"""

    with open(OUTPUT_NETWORKLINK, "w", encoding="utf-8") as f:
        f.write(networklink)

    print(f"Wrote {OUTPUT_KML} and {OUTPUT_NETWORKLINK}. Skipped {bad_rows} rows with invalid lat/lon.")

if __name__ == "__main__":
    main()
