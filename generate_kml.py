#!/usr/bin/env python3
import csv
import html
import os
import sys
import urllib.request
from datetime import datetime, timezone

# -----------------------
# High-level configuration
# -----------------------
DATASET_NAME = "FLG/TwiceAsNice MeshCore Site Map"
NETWORKLINK_NAME = f"{DATASET_NAME} (Live)"

PROSPECTIVE_CSV_URL = os.environ.get("PROSPECTIVE_CSV_URL", "").strip()
INSTALLED_CSV_URL = os.environ.get("INSTALLED_CSV_URL", "").strip()

OUTPUT_KML = "sites.kml"
OUTPUT_NETWORKLINK = "networklink.kml"
DATASET_URL = os.environ.get("DATASET_URL", "").strip()

REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "600"))

# -----------------------
# Prospective node styling
# -----------------------
PROSPECTIVE_CATEGORY_ORDER = [
    "Suggested",
    "Group Approved",
    "Group Rejected",
    "Owner Requested",
    "Owner Approved",
    "Owner Rejected",
    # NOTE: "Node Installed" removed from prospective sheet by design
]

# Using your exact values as provided earlier
PROSPECTIVE_CATEGORY_COLORS = {
    "Owner Approved": "ff00ff00",
    "Group Approved": "fffeb900",
    "Node Installed": "ff00ff00",   # unused in prospective if you move installed out
    "Suggested": "ffeeff00",
    "Owner Requested": "ffda00ff",
    "Owner Rejected": "ff000000",
    "Group Rejected": "ff0000ff",
}

PROSPECTIVE_DEFAULT_ICON_URL = "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png"

PROSPECTIVE_CATEGORY_ICONS = {
    "Node Installed": "http://maps.google.com/mapfiles/kml/paddle/grn-stars.png",  # unused here typically
    "Owner Approved": "http://maps.google.com/mapfiles/kml/paddle/grn-blank.png",
    "Suggested": "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png",
    "Owner Rejected": "http://maps.google.com/mapfiles/kml/paddle/X.png",
    "Group Rejected": "http://maps.google.com/mapfiles/kml/paddle/X.png",
}

# -----------------------
# Installed node styling
# -----------------------
# Folder by Node Class (order is optional; if not listed, it will sort after)
NODE_CLASS_ORDER = [
    "Backbone",
    "Branch",
    "Home/Office Repeater",
    "Room Server",
]

# Style by Node Status (includes "Pre-Install")
# KML colors are AABBGGRR (alpha, blue, green, red)
INSTALLED_STATUS_COLORS = {
    "In Service": "ff00ff00",         # Green
    "Pre-Install": "ffeeff00",        # Light Blue-ish (matches your suggested)
    "Needs Updates": "ff00ffff",      # Yellow (BGRR -> 00ffff = yellow)
    "Offline for Repair": "ff00a5ff", # Orange-ish
    "Needs Repair": "ff0000ff",       # Red
    "Decommissioned": "ff808080",     # Gray
}

INSTALLED_DEFAULT_ICON_URL = "http://maps.google.com/mapfiles/kml/paddle/wht-blank.png"

# If you ever want status-specific shapes, add them here. Otherwise everything uses default icon URL.
INSTALLED_STATUS_ICONS = {
    # Example if you later want: "In Service": "http://maps.google.com/mapfiles/kml/paddle/grn-stars.png"
}

# -----------------------
# Required columns
# -----------------------
PROSPECTIVE_REQUIRED_COLUMNS = ["Name", "Latitude", "Longitude", "Category"]
INSTALLED_REQUIRED_COLUMNS = ["Node ID", "Node Name", "Latitude", "Longitude", "Node Class", "Node Status"]

# -----------------------
# Helpers
# -----------------------
def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_csv(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8", errors="replace")

def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def opt(row: dict, cols: set, col: str) -> str:
    return (row.get(col) or "").strip() if col in cols else ""

def sort_key_with_preferred_order(value: str, preferred: list) -> tuple:
    try:
        return (0, preferred.index(value))
    except ValueError:
        return (1, value.lower())

def style_id(prefix: str, name: str) -> str:
    # KML id can contain spaces, but keeping it predictable helps debugging.
    return f"{prefix}{name}"

def build_style_block(style_id_str: str, color: str, icon_url: str) -> str:
    return f"""
    <Style id="{html.escape(style_id_str)}">
      <IconStyle>
        <color>{color}</color>
        <scale>1.1</scale>
        <Icon><href>{html.escape(icon_url)}</href></Icon>
      </IconStyle>
      <LabelStyle><scale>0.9</scale></LabelStyle>
    </Style>"""

def main() -> None:
    if not PROSPECTIVE_CSV_URL:
        die("PROSPECTIVE_CSV_URL env var is required")
    if not INSTALLED_CSV_URL:
        die("INSTALLED_CSV_URL env var is required")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    # -----------------------
    # Read Prospective sheet
    # -----------------------
    p_text = fetch_csv(PROSPECTIVE_CSV_URL)
    p_reader = csv.DictReader(p_text.splitlines())
    p_cols = set(p_reader.fieldnames or [])
    missing_p = [c for c in PROSPECTIVE_REQUIRED_COLUMNS if c not in p_cols]
    if missing_p:
        die(f"Prospective sheet missing required columns: {missing_p}. Found: {sorted(p_cols)}")

    prospective_folders = {}  # category -> list[(sort_key, placemark_xml)]
    prospective_skipped = 0

    for row in p_reader:
        name = (row.get("Name") or "").strip()
        category = (row.get("Category") or "").strip()
        lat = safe_float(row.get("Latitude"))
        lon = safe_float(row.get("Longitude"))

        if not name or not category or lat is None or lon is None:
            prospective_skipped += 1
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            prospective_skipped += 1
            continue

        address = opt(row, p_cols, "Street Address")
        notes = opt(row, p_cols, "Notes")
        proposed_by = opt(row, p_cols, "Proposed By")
        assigned_to = opt(row, p_cols, "Assigned To")
        node_owner = opt(row, p_cols, "Node Owner")
        installed_node_name = opt(row, p_cols, "Installed Node Name")
        fcc_id = opt(row, p_cols, "FCC ID")
        fcc_link = opt(row, p_cols, "FCC Link")

        desc_parts = [
            f"<b>Name:</b> {html.escape(name)}",
            f"<b>Category:</b> {html.escape(category)}",
        ]
        if address: desc_parts.append(f"<b>Street Address:</b> {html.escape(address)}")
        if proposed_by: desc_parts.append(f"<b>Proposed By:</b> {html.escape(proposed_by)}")
        if assigned_to: desc_parts.append(f"<b>Assigned To:</b> {html.escape(assigned_to)}")
        if node_owner: desc_parts.append(f"<b>Node Owner:</b> {html.escape(node_owner)}")
        if installed_node_name: desc_parts.append(f"<b>Installed Node Name:</b> {html.escape(installed_node_name)}")
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

        # Styles are category-based for Prospective
        p_style = ""
        if category in PROSPECTIVE_CATEGORY_COLORS:
            p_style = f"#{style_id('p-cat-', category)}"

        placemark = f"""
      <Placemark>
        <name>{html.escape(name)}</name>
        {"<styleUrl>"+html.escape(p_style)+"</styleUrl>" if p_style else ""}
        <description><![CDATA[{desc}]]></description>
        <Point><coordinates>{lon},{lat}</coordinates></Point>
      </Placemark>"""

        prospective_folders.setdefault(category, []).append((name.lower(), placemark))

    # -----------------------
    # Read Installed sheet
    # -----------------------
    i_text = fetch_csv(INSTALLED_CSV_URL)
    i_reader = csv.DictReader(i_text.splitlines())
    i_cols = set(i_reader.fieldnames or [])
    missing_i = [c for c in INSTALLED_REQUIRED_COLUMNS if c not in i_cols]
    if missing_i:
        die(f"Installed sheet missing required columns: {missing_i}. Found: {sorted(i_cols)}")

    installed_folders = {}  # node_class -> list[(sort_key, placemark_xml)]
    installed_skipped = 0

    for row in i_reader:
        node_id = (row.get("Node ID") or "").strip()
        node_name = (row.get("Node Name") or "").strip()
        node_class = (row.get("Node Class") or "").strip()
        node_status = (row.get("Node Status") or "").strip()

        lat = safe_float(row.get("Latitude"))
        lon = safe_float(row.get("Longitude"))

        if not node_id or not node_name or not node_class or not node_status or lat is None or lon is None:
            installed_skipped += 1
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            installed_skipped += 1
            continue

        # Contact / ownership fields you requested
        node_owner = opt(row, i_cols, "Node Owner")
        site_owner = opt(row, i_cols, "Site Owner")
        site_contact_name = opt(row, i_cols, "Site Contact Name")
        site_contact_phone = opt(row, i_cols, "Site Contact Phone")
        site_contact_email = opt(row, i_cols, "Site Contact Email")

        # Optional tech/inventory fields (present if you add them; safe if absent)
        baseboard = opt(row, i_cols, "Node Baseboard")
        antenna = opt(row, i_cols, "Antenna")
        antenna_gain = opt(row, i_cols, "Antenna Gain")
        battery_type = opt(row, i_cols, "Battery Type")
        battery_qty = opt(row, i_cols, "Battery Quantity")
        solar = opt(row, i_cols, "Solar")
        solar_wattage = opt(row, i_cols, "Solar Panel Wattage")
        install_type = opt(row, i_cols, "Installation Type")
        install_elev = opt(row, i_cols, "Installed Elevation")
        installed_date = opt(row, i_cols, "Installed Date")
        last_updated_date = opt(row, i_cols, "Last Updated Date") or opt(row, i_cols, "Late Updated Date")
        decommissioned_date = opt(row, i_cols, "Decommissioned Date")

        fcc_id = opt(row, i_cols, "FCC ID")
        fcc_link = opt(row, i_cols, "FCC Link")
        notes = opt(row, i_cols, "Notes")

        desc_parts = [
            f"<b>Node Name:</b> {html.escape(node_name)}",
            f"<b>Node ID:</b> {html.escape(node_id)}",
            f"<b>Node Class:</b> {html.escape(node_class)}",
            f"<b>Node Status:</b> {html.escape(node_status)}",
        ]

        if node_owner: desc_parts.append(f"<b>Node Owner:</b> {html.escape(node_owner)}")
        if site_owner: desc_parts.append(f"<b>Site Owner:</b> {html.escape(site_owner)}")
        if site_contact_name: desc_parts.append(f"<b>Site Contact Name:</b> {html.escape(site_contact_name)}")
        if site_contact_phone: desc_parts.append(f"<b>Site Contact Phone:</b> {html.escape(site_contact_phone)}")
        if site_contact_email: desc_parts.append(f"<b>Site Contact Email:</b> {html.escape(site_contact_email)}")

        if baseboard: desc_parts.append(f"<b>Node Baseboard:</b> {html.escape(baseboard)}")
        if antenna: desc_parts.append(f"<b>Antenna:</b> {html.escape(antenna)}")
        if antenna_gain: desc_parts.append(f"<b>Antenna Gain:</b> {html.escape(antenna_gain)}")
        if battery_type: desc_parts.append(f"<b>Battery Type:</b> {html.escape(battery_type)}")
        if battery_qty: desc_parts.append(f"<b>Battery Quantity:</b> {html.escape(battery_qty)}")
        if solar: desc_parts.append(f"<b>Solar:</b> {html.escape(solar)}")
        if solar_wattage: desc_parts.append(f"<b>Solar Panel Wattage:</b> {html.escape(solar_wattage)}")
        if install_type: desc_parts.append(f"<b>Installation Type:</b> {html.escape(install_type)}")
        if install_elev: desc_parts.append(f"<b>Installed Elevation:</b> {html.escape(install_elev)}")
        if installed_date: desc_parts.append(f"<b>Installed Date:</b> {html.escape(installed_date)}")
        if last_updated_date: desc_parts.append(f"<b>Last Updated Date:</b> {html.escape(last_updated_date)}")
        if decommissioned_date: desc_parts.append(f"<b>Decommissioned Date:</b> {html.escape(decommissioned_date)}")

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

        # Installed styles are status-based
        i_style = ""
        if node_status in INSTALLED_STATUS_COLORS:
            i_style = f"#{style_id('i-status-', node_status)}"

        placemark = f"""
      <Placemark>
        <name>{html.escape(node_name)}</name>
        {"<styleUrl>"+html.escape(i_style)+"</styleUrl>" if i_style else ""}
        <description><![CDATA[{desc}]]></description>
        <Point><coordinates>{lon},{lat}</coordinates></Point>
      </Placemark>"""

        installed_folders.setdefault(node_class, []).append((node_name.lower(), placemark))

    # -----------------------
    # Build styles
    # -----------------------
    style_blocks = []

    # Prospective category styles
    for cat, color in PROSPECTIVE_CATEGORY_COLORS.items():
        sid = style_id("p-cat-", cat)
        icon_url = PROSPECTIVE_CATEGORY_ICONS.get(cat, PROSPECTIVE_DEFAULT_ICON_URL)
        style_blocks.append(build_style_block(sid, color, icon_url))

    # Installed status styles
    for status, color in INSTALLED_STATUS_COLORS.items():
        sid = style_id("i-status-", status)
        icon_url = INSTALLED_STATUS_ICONS.get(status, INSTALLED_DEFAULT_ICON_URL)
        style_blocks.append(build_style_block(sid, color, icon_url))

    styles_xml = "\n".join(style_blocks)

    # -----------------------
    # Build folder XML
    # -----------------------
    # Prospective: subfolders by category, stable order you defined, then any extras
    p_categories = sorted(prospective_folders.keys(), key=lambda c: sort_key_with_preferred_order(c, PROSPECTIVE_CATEGORY_ORDER))
    p_folder_parts = []
    for cat in p_categories:
        entries = prospective_folders[cat]
        entries.sort(key=lambda x: x[0])  # A-Z by name
        pms = "".join(pm for _, pm in entries)
        p_folder_parts.append(f"""
      <Folder>
        <name>{html.escape(cat)}</name>
        <visibility>1</visibility>
        <open>0</open>
        {pms}
      </Folder>""")
    prospective_xml = f"""
    <Folder>
      <name>Prospective Nodes</name>
      <visibility>1</visibility>
      <open>0</open>
      {''.join(p_folder_parts)}
    </Folder>"""

    # Installed: folders by Node Class (stable preferred order), within each A-Z by Node Name
    i_classes = sorted(installed_folders.keys(), key=lambda c: sort_key_with_preferred_order(c, NODE_CLASS_ORDER))
    i_folder_parts = []
    for cls in i_classes:
        entries = installed_folders[cls]
        entries.sort(key=lambda x: x[0])  # A-Z by node name
        pms = "".join(pm for _, pm in entries)
        i_folder_parts.append(f"""
      <Folder>
        <name>{html.escape(cls)}</name>
        <visibility>1</visibility>
        <open>0</open>
        {pms}
      </Folder>""")
    installed_xml = f"""
    <Folder>
      <name>Installed Nodes</name>
      <visibility>1</visibility>
      <open>0</open>
      {''.join(i_folder_parts)}
    </Folder>"""

    # -----------------------
    # Emit sites.kml
    # -----------------------
    sites_kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{html.escape(DATASET_NAME)}</name>
    <open>1</open>
    <description><![CDATA[
      Live dataset generated from Google Sheets.<br/>
      Updated (UTC): {now}<br/>
      Prospective rows skipped: {prospective_skipped}<br/>
      Installed rows skipped: {installed_skipped}
    ]]></description>
{styles_xml}
{prospective_xml}
{installed_xml}
  </Document>
</kml>
"""
    with open(OUTPUT_KML, "w", encoding="utf-8") as f:
        f.write(sites_kml)

    # -----------------------
    # Emit networklink.kml
    # -----------------------
    href = DATASET_URL or "https://txkbaldlaw.github.io/meshnodes-site-map/sites.kml"
    networklink_kml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
        f.write(networklink_kml)

if __name__ == "__main__":
    main()
