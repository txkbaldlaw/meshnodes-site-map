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
CATEGORY_COLORS = {
    "Owner Approved": "ff90ee90",     # Light Green
    "Group Approved": "ffe6add8",     # Lavender
    "Node Installed": "ff006400",     # Dark Green
    "Suggested": "ffadd8e6",          # Light Blue
    "Owner Requested": "ff00a5ff",    # Orange
    "Owner Rejected": "ff0000ff",     # Red
    "Group Rejected": "ff000000",     # Black
}

# Only these fields are REQUIRED to exist as columns in the sheet:
REQUIRED_COLUMNS = [
    "Name",
    "Latitude",
    "Longitude",
    "Category",
]

# These are OPTIONAL columns. If present, they will be shown in placemark balloons.
OPTIONAL_COLUMNS = [
    "Street Address",
    "Notes",
    "Installed Node Name",
    "Proposed By",
    "Assigned To",
    "Node Owner",
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

        # Optional fields (may be blank or even missing as columns)
        address = (row.get("Street Address") or "").strip() if "Street Address" in cols else ""
        notes = (row.get("Notes") or "").strip() if "Notes" in cols else ""
        installed_node = (row.get("Installed Node Name") or "").strip() if "Installed Node Name" in cols else ""
        proposed_by = (row.get("Proposed By") or "").strip() if "Proposed By" in cols else ""
        assigned_to = (row.get("Assigned To") or "").strip() if "Assigned To" in cols else ""
        node_owner = (row.get("Node Owner") or "").strip() if "Node Owner" in cols else ""

        # Style by category (unknown categories still render, just without color styling)
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
