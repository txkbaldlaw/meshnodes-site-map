#!/usr/bin/env python3
import csv
import html
import os
import sys
import urllib.request
from datetime import datetime, timezone

DATASET_NAME = "FLG/TwiceAsNice MeshCore Site Map"
NETWORKLINK_NAME = f"{DATASET_NAME} (Live)"

CSV_URL = os.environ.get("SHEET_CSV_URL", "").strip()
OUTPUT_KML = "sites.kml"
OUTPUT_NETWORKLINK = "networklink.kml"
DATASET_URL = os.environ.get("DATASET_URL", "").strip()
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "600"))

CATEGORY_ORDER = [
    "Suggested",
    "Group Approved",
    "Group Rejected",
    "Owner Requested",
    "Owner Approved",
    "Owner Rejected",
    "Node Installed",
]

CATEGORY_COLORS = {
    "Owner Approved": "ff00ff00",
    "Group Approved": "fffeb900",
    "Node Installed": "ff00ff00",
    "Suggested": "ffeeff00",
    "Owner Requested": "ffda00ff",
    "Owner Rejected": "ff000000",
    "Group Rejected": "ff0000ff",
}

DEFAULT_ICON_URL = "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png"

CATEGORY_ICONS = {
    "Node Installed": "http://maps.google.com/mapfiles/kml/paddle/grn-stars.png",
    "Owner Approved": "http://maps.google.com/mapfiles/kml/paddle/grn-blank.png",
    "Suggested": "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png",
    "Owner Rejected": "http://maps.google.com/mapfiles/kml/paddle/X.png",
    "Group Rejected": "http://maps.google.com/mapfiles/kml/paddle/X.png",
}

REQUIRED_COLUMNS = ["Name", "Latitude", "Longitude", "Category"]

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_csv(url):
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8", errors="replace")

def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def category_sort_key(cat):
    try:
        return (0, CATEGORY_ORDER.index(cat))
    except ValueError:
        return (1, cat.lower())

def build_styles():
    out = []
    for cat, color in CATEGORY_COLORS.items():
        icon = CATEGORY_ICONS.get(cat, DEFAULT_ICON_URL)
        out.append(f"""
    <Style id="{html.escape(cat)}">
      <IconStyle>
        <color>{color}</color>
        <scale>1.1</scale>
        <Icon><href>{html.escape(icon)}</href></Icon>
      </IconStyle>
      <LabelStyle><scale>0.9</scale></LabelStyle>
    </Style>""")
    return "\n".join(out)

def main():
    if not CSV_URL:
        die("SHEET_CSV_URL env var is required")

    csv_text = fetch_csv(CSV_URL)
    reader = csv.DictReader(csv_text.splitlines())
    cols = reader.fieldnames or []

    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        die(f"Missing required columns: {missing}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    folders = {}
    skipped = 0

    def opt(row, col):
        return (row.get(col) or "").strip() if col in cols else ""

    for row in reader:
        name = (row.get("Name") or "").strip()
        category = (row.get("Category") or "").strip()
        lat = safe_float(row.get("Latitude"))
        lon = safe_float(row.get("Longitude"))

        if not name or not category or lat is None or lon is None:
            skipped += 1
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            skipped += 1
            continue

        address = opt(row, "Street Address")
        notes = opt(row, "Notes")
        installed_node = opt(row, "Installed Node Name")
        proposed_by = opt(row, "Proposed By")
        assigned_to = opt(row, "Assigned To")
        node_owner = opt(row, "Node Owner")
        fcc_id = opt(row, "FCC ID")
        fcc_link = opt(row, "FCC Link")

        desc_parts = [
            f"<b>Name:</b> {html.escape(name)}",
            f"<b>Status:</b> {html.escape(category)}",
        ]
        if address: desc_parts.append(f"<b>Street Address:</b> {html.escape(address)}")
        if proposed_by: desc_parts.append(f"<b>Proposed By:</b> {html.escape(proposed_by)}")
        if assigned_to: desc_parts.append(f"<b>Assigned To:</b> {html.escape(assigned_to)}")
        if node_owner: desc_parts.append(f"<b>Node Owner:</b> {html.escape(node_owner)}")
        if installed_node: desc_parts.append(f"<b>Installed Node Name:</b> {html.escape(installed_node)}")
        if fcc_id: desc_parts.append(f"<b>FCC ID:</b> {html.escape(fcc_id)}")
        if fcc_link:
            u = html.escape(fcc_link, quote=True)
            desc_parts.append(f'<b>FCC Link:</b> <a href="{u}" target="_blank">{u}</a>')
        if notes: desc_parts.append(f"<b>Notes:</b> {html.escape(notes)}")

        desc_parts.extend([
            f"<i>Updated (UTC):</i> {now}",
            f"<i>Refresh:</i> every {REFRESH_SECONDS // 60} minutes",
        ])

        desc = "<br/>".join(desc_parts)
        style_url = f"#{category}" if category in CATEGORY_COLORS else ""

        placemark = f"""
      <Placemark>
        <name>{html.escape(name)}</name>
        {"<styleUrl>"+html.escape(style_url)+"</styleUrl>" if style_url else ""}
        <description><![CDATA[{desc}]]></description>
        <Point><coordinates>{lon},{lat}</coordinates></Point>
      </Placemark>"""

        folders.setdefault(category, []).append((name.lower(), placemark))

    folders_xml = []
    for cat in sorted(folders.keys(), key=category_sort_key):
        entries = folders[cat]
        entries.sort(key=lambda x: x[0])
        pms = "".join(pm for _, pm in entries)
        folders_xml.append(f"""
    <Folder>
      <name>{html.escape(cat)}</name>
      <visibility>1</visibility>
      <open>0</open>
      {pms}
    </Folder>""")

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{html.escape(DATASET_NAME)}</name>
    <open>1</open>
    <description><![CDATA[
      Live dataset generated from Google Sheets.<br/>
      Updated (UTC): {now}<br/>
      Rows skipped: {skipped}
    ]]></description>
{build_styles()}
{''.join(folders_xml)}
  </Document>
</kml>
"""
    with open(OUTPUT_KML, "w", encoding="utf-8") as f:
        f.write(kml)

    href = DATASET_URL or "https://txkbaldlaw.github.io/meshnodes-site-map/sites.kml"
    networklink = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <NetworkLink>
    <name>{html.escape(NETWORKLINK_NAME)}</name>
    <Link>
      <href>{html.escape(href)}</href>
      <refreshMode>onInterval</refreshMode>
      <refreshInterval>{REFRESH_SECONDS}</refreshInterval>
    </Link>
  </NetworkLink>
</kml>
"""
    with open(OUTPUT_NETWORKLINK, "w", encoding="utf-8") as f:
        f.write(networklink)

if __name__ == "__main__":
    main()
