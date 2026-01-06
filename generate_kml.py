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

# Public URL to sites.kml on GitHub Pages (set as repo variable DATASET_URL)
DATASET_URL = os.environ.get("DATASET_URL", "").strip()

# 10 minutes = 600 seconds
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "600"))

# Category -> KML colors in AABBGGRR (alpha, blue, green, red)
# NOTE: Using your exact values as provided (including comment labels).
CATEGORY_COLORS = {
    "Owner Approved": "ff00ff00",     # Pure Green
    "Group Approved": "fffeb900",     # Mid Blue
    "Node Installed": "ff00ff00",     # Pure Green
    "Suggested": "ffeeff00",          # Light Blue
    "Owner Requested": "ffda00ff",    # Purple
    "Owner Rejected": "ff000000",     # Red
    "Group Rejected": "ff0000ff",     # Black
}

# Category icon URLs (Google Earth / KML built-in icons)
# Any category not listed here will use DEFAULT_ICON_URL.
DEFAULT_ICON_URL = "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png"

# Category Shapes
CATEGORY_ICONS = {
    "Node Installed": "http://maps.google.com/mapfiles/kml/paddle/grn-stars.png",
    "Owner Approved": "http://maps.google.com/mapfiles/kml/paddle/grn-blank.png",
    "Suggested": "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png",
    "Owner Rejected": "http://maps.google.com/mapfiles/kml/paddle/X.png",
    "Group Rejected": "http://maps.google.com/mapfiles/kml/paddle/X.png",
}

# Only these fields are REQUIRED to exist as columns in the sheet:
REQUIRED_COLUMNS = [
    "Name",
    "Latitude",
    "Longitude",
    "Category",
]

def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_csv(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8", errors="replace")

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

def build_styles() -> str:
    out = []
    for cat, color in CATEGORY_COLORS.items():
        icon_url = CATEGORY_ICONS.get(cat, DEFAULT_ICON_URL)
        out.append(f"""
    <Style id="{html.escape(cat)}">
      <IconStyle>
        <color>{color}</color>
        <scale>1.1</scale>
        <Icon>
          <href>{html.escape(icon_url)}</href>
        </Icon>
      </IconStyle>
      <LabelStyle>
        <scale>0.9</scale>
      </LabelStyle>
    </Style>""")
    return "\n".join(out)

def main() -> None:
    if not CSV_URL:
        die("SHEET_CSV_URL env var is required (your published CSV link).")

    csv_text = fetch_csv(CSV_URL)
    reader = csv.DictReader(csv_text.splitlines())

    cols = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        die(f"Missing required columns in CSV: {missing}. Found: {cols}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    placemarks = []
    skipped = 0

    for i, row in enumerate(reader, start=2):
        # Required fields (must be non-blank)
        name = (row.get("Name") or "").strip()
        category = (row.get("Category") or "").strip()

        lat = safe_float(row.get("Latitude"))
        lon = safe_float(row.get("Longitude"))

        if not name or not category or lat is None or lon is None:
            skipped += 1
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            skipped += 1
            continue

        # Optional fields (may be blank; column may or may not exist)
        def opt(col: str) -> str:
            return (row.get(col) or "").strip() if col in cols else ""

        address = opt("Street Address")
        notes = opt("Notes")
        installed_node = opt("Installed Node Name")
        proposed_by = opt("Proposed By")
        assigned_to = opt("Assigned To")
        node_owner = opt("Node Owner")
        fcc_id = opt("FCC ID")
        fcc_link = opt("FCC Link")

        # Style by category (unknown categories still render, just without styling)
        style_url = f"#{category}" if category in CATEGORY_COLORS else ""

        # Build description with only populated fields
        desc_parts = [
            f"<b>Name:</b> {html.escape(name)}",
            f"<b>Status:</b> {html.escape(category)}",
        ]

        if address:
            desc_parts.append(f"<b>Street Address:</b> {html.escape(address)}")
        if proposed_by:
            desc_parts.append(f"<b>Proposed By:</b> {html.escape(proposed_by)}")
        if assigned_to:
            desc_parts.append(f"<b>Assigned To:</b> {html.escape(assigned_to)}")
        if node_owner:
            desc_parts.append(f"<b>Node Owner:</b> {html.escape(node_owner)}")
        if installed_node:
            desc_parts.append(f"<b>Installed Node Name:</b> {html.escape(installed_node)}")
        if fcc_id:
            desc_parts.append(f"<b>FCC ID:</b> {html.escape(fcc_id)}")
        if fcc_link:
            safe_url = html.escape(fcc_link, quote=True)
            desc_parts.append(
                f'<b>FCC Link:</b> <a href="{safe_url}" target="_blank">{safe_url}</a>'
            )
        if notes:
            desc_parts.append(f"<b>Notes:</b> {html.escape(notes)}")

        desc_parts.extend([
            f"<i>Updated (UTC):</i> {now}",
            f"<i>Refresh:</i> every {REFRESH_SECONDS // 60} minutes",
        ])

        desc = "<br/>".join(desc_parts)

        placemarks.append(f"""
    <Placemark>
      <name>{html.escape(name)}</name>
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
      Rows skipped (missing/invalid required fields): {skipped}
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

    print(f"Wrote {OUTPUT_KML} and {OUTPUT_NETWORKLINK}. Skipped {skipped} rows missing required fields.")

if __name__ == "__main__":
    main()
