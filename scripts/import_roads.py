#!/usr/bin/env python3
"""
Import SA Road Network from data.sa.gov.au into the PostgreSQL database.

Downloads the statewide road network shapefile and imports road names,
types, suburbs, and geometries into the sa_roads table for local geocoding.

Usage:
    python scripts/import_roads.py [--shapefile PATH]
"""

import argparse
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import psycopg2
import shapefile  # pyshp


# data.sa.gov.au resource URL for the roads shapefile
ROADS_RESOURCE_URL = "https://data.sa.gov.au/data/dataset/roads/resource/dbd6cc0f-317e-4fc7-b734-b81a518a3f00"

# Common road type abbreviation normalization
ROAD_TYPE_MAP = {
    'RD': 'ROAD', 'ST': 'STREET', 'AV': 'AVENUE', 'AVE': 'AVENUE',
    'DR': 'DRIVE', 'CT': 'COURT', 'PL': 'PLACE', 'CR': 'CRESCENT',
    'CRES': 'CRESCENT', 'TCE': 'TERRACE', 'TER': 'TERRACE',
    'HWY': 'HIGHWAY', 'BVD': 'BOULEVARD', 'BLVD': 'BOULEVARD',
    'CL': 'CLOSE', 'GR': 'GROVE', 'GRV': 'GROVE', 'LN': 'LANE',
    'WY': 'WAY', 'CIR': 'CIRCLE', 'PKY': 'PARKWAY', 'PKWY': 'PARKWAY',
    'PDE': 'PARADE', 'ESP': 'ESPLANADE',
}

# Fields to look for in shapefile (varies by data source)
NAME_FIELDS = ['ROAD_NAME', 'NAME', 'ROADNAME', 'STR_NAME', 'LABEL', 'ROAD_NM']
TYPE_FIELDS = ['ROAD_TYPE', 'TYPE', 'ROADTYPE', 'STR_TYPE', 'CLASS', 'ROAD_TP']
SUBURB_FIELDS = ['SUBURB', 'LOCALITY', 'LOC_NAME', 'SUBURB_L', 'SUBURB_R',
                 'LEFT_LOC', 'RIGHT_LOC', 'L_LOCALITY', 'R_LOCALITY']

SUBURBS_CSV_URL = "https://data.sa.gov.au/data/dataset/e4d3a355-29d7-4bdc-a81d-13fd5ed09ef9/resource/58b3b8ef-f292-4e27-a7bc-215ad7670cda/download/suburbs.csv"

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://sagrn:password@localhost:5432/sagrn'
)


def get_pg_dsn():
    """Convert async DATABASE_URL to sync psycopg2 DSN."""
    url = DATABASE_URL
    # Strip async driver prefix
    url = url.replace('postgresql+asyncpg://', 'postgresql://')
    url = url.replace('postgres+asyncpg://', 'postgresql://')
    return url


def load_suburb_id_map():
    """Download suburb CSV and build suburb_num -> suburb_name mapping."""
    print("Downloading suburb ID mapping from data.sa.gov.au...")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(SUBURBS_CSV_URL)
        if resp.status_code != 200:
            print("WARNING: Could not download suburbs CSV, roads will have no suburb info")
            return {}

    mapping = {}
    import csv as csv_mod
    reader = csv_mod.DictReader(resp.text.strip().splitlines())
    for row in reader:
        suburb_num = row.get('suburb_num', '').strip()
        suburb_name = row.get('suburb', '').strip().upper()
        if suburb_num and suburb_name:
            mapping[int(suburb_num)] = suburb_name

    print(f"  Loaded {len(mapping)} suburb ID mappings")
    return mapping


def find_field(field_names, candidates):
    """Find the first matching field name from candidates (case-insensitive)."""
    upper_names = {f.upper(): f for f in field_names}
    for candidate in candidates:
        if candidate.upper() in upper_names:
            return upper_names[candidate.upper()]
    return None


def download_shapefile(output_dir):
    """Download the SA roads shapefile from data.sa.gov.au."""
    print("Fetching download URL from data.sa.gov.au...")

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        # Try the CKAN API to get the resource download URL
        api_url = "https://data.sa.gov.au/data/api/3/action/resource_show"
        resp = client.get(api_url, params={"id": "dbd6cc0f-317e-4fc7-b734-b81a518a3f00"})

        if resp.status_code == 200:
            data = resp.json()
            download_url = data.get('result', {}).get('url', '')
        else:
            # Fallback: try common direct download patterns
            download_url = "https://data.sa.gov.au/data/dataset/roads/resource/dbd6cc0f-317e-4fc7-b734-b81a518a3f00/download/"

        if not download_url:
            print("ERROR: Could not determine download URL.")
            print("Please download the roads shapefile manually from:")
            print("  https://data.sa.gov.au/data/dataset/roads")
            print(f"  and extract to: {output_dir}")
            sys.exit(1)

        print(f"Downloading from: {download_url}")
        resp = client.get(download_url)

        if resp.status_code != 200:
            print(f"ERROR: Download failed with status {resp.status_code}")
            print("Please download manually from: https://data.sa.gov.au/data/dataset/roads")
            sys.exit(1)

        content = resp.content

    # Check if it's a zip file
    if content[:2] == b'PK':
        print(f"Extracting shapefile ({len(content) / 1024 / 1024:.1f} MB)...")
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(output_dir)
        print(f"Extracted to {output_dir}")
    else:
        # Might be a direct .shp file or other format
        shp_path = os.path.join(output_dir, "roads.shp")
        with open(shp_path, 'wb') as f:
            f.write(content)
        print(f"Saved to {shp_path}")

    # Find the .shp file — prefer GDA94 (has data) over GDA2020 (may be empty)
    shp_files = []
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.lower().endswith('.shp'):
                shp_files.append(os.path.join(root, f))

    if not shp_files:
        print("ERROR: No .shp file found in download")
        sys.exit(1)

    # Prefer files with data (larger size) — GDA2020 shp can be empty
    shp_files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    chosen = shp_files[0]
    print(f"Using shapefile: {os.path.basename(chosen)} ({os.path.getsize(chosen) / 1024 / 1024:.1f} MB)")
    return chosen


def coords_to_wkt(points):
    """Convert a list of (x, y) points to WKT LineString."""
    if not points or len(points) < 2:
        return None
    coord_str = ', '.join(f'{x} {y}' for x, y in points)
    return f'LINESTRING ({coord_str})'


def import_roads(shp_path):
    """Import roads from shapefile into PostgreSQL database."""
    print(f"Reading shapefile: {shp_path}")
    sf = shapefile.Reader(shp_path)

    # Identify relevant fields
    field_names = [f[0] for f in sf.fields[1:]]  # Skip DeletionFlag
    print(f"Fields found: {field_names}")

    name_field = find_field(field_names, NAME_FIELDS)
    type_field = find_field(field_names, TYPE_FIELDS)
    suburb_field = find_field(field_names, SUBURB_FIELDS)

    if not name_field:
        print(f"ERROR: Could not find road name field. Available: {field_names}")
        print("Try one of these field names for the road name column.")
        sys.exit(1)

    print(f"Using fields - Name: {name_field}, Type: {type_field}, Suburb: {suburb_field}")

    # Get field indices
    field_idx = {f[0]: i for i, f in enumerate(sf.fields[1:])}
    name_idx = field_idx[name_field]
    type_idx = field_idx.get(type_field) if type_field else None
    suburb_idx = field_idx.get(suburb_field) if suburb_field else None

    # Check for secondary suburb field (left/right side of road)
    suburb_r_field = None
    for candidate in ['SUBURB_R', 'RIGHT_LOC', 'R_LOCALITY', 'suburbidri']:
        if candidate in field_idx:
            suburb_r_field = candidate
            break
    suburb_r_idx = field_idx.get(suburb_r_field) if suburb_r_field else None

    # Also check for numeric suburb ID fields (suburbidle/suburbidri from DPTI data)
    suburb_id_l_idx = field_idx.get('suburbidle')
    suburb_id_r_idx = field_idx.get('suburbidri')
    suburb_id_map = {}
    if suburb_id_l_idx is not None or suburb_id_r_idx is not None:
        suburb_id_map = load_suburb_id_map()

    # Connect to PostgreSQL
    conn = psycopg2.connect(get_pg_dsn())
    cur = conn.cursor()

    # Truncate existing data
    cur.execute("TRUNCATE TABLE sa_roads RESTART IDENTITY")
    conn.commit()

    inserted = 0
    skipped = 0
    batch = []

    for sr in sf.iterShapeRecords():
        rec = sr.record
        shp = sr.shape

        road_name = rec[name_idx]
        if not road_name or not isinstance(road_name, str):
            skipped += 1
            continue

        road_name = road_name.strip().upper()
        if not road_name:
            skipped += 1
            continue

        # Extract road type
        road_type = None
        if type_idx is not None:
            road_type = rec[type_idx]
            if road_type and isinstance(road_type, str):
                road_type = road_type.strip().upper()
                road_type = ROAD_TYPE_MAP.get(road_type, road_type)
            else:
                road_type = None

        # If road type is embedded in the name, separate it
        if not road_type:
            parts = road_name.rsplit(' ', 1)
            if len(parts) == 2 and parts[1] in ROAD_TYPE_MAP:
                road_name = parts[0]
                road_type = ROAD_TYPE_MAP[parts[1]]
            elif len(parts) == 2 and parts[1] in ROAD_TYPE_MAP.values():
                road_name = parts[0]
                road_type = parts[1]

        # Extract suburb(s)
        suburbs = set()
        if suburb_idx is not None:
            s = rec[suburb_idx]
            if s and isinstance(s, str) and s.strip() and not s.strip().isdigit():
                suburbs.add(s.strip().upper())
        if suburb_r_idx is not None:
            s = rec[suburb_r_idx]
            if s and isinstance(s, str) and s.strip() and not s.strip().isdigit():
                suburbs.add(s.strip().upper())

        # Handle numeric suburb IDs from DPTI roads data
        if not suburbs and suburb_id_map:
            if suburb_id_l_idx is not None:
                sid = rec[suburb_id_l_idx]
                if sid and isinstance(sid, (int, float)):
                    name = suburb_id_map.get(int(sid))
                    if name:
                        suburbs.add(name)
            if suburb_id_r_idx is not None:
                sid = rec[suburb_id_r_idx]
                if sid and isinstance(sid, (int, float)):
                    name = suburb_id_map.get(int(sid))
                    if name:
                        suburbs.add(name)

        if not suburbs:
            suburbs = {None}

        # Get geometry
        if shp.shapeType in (3, 13, 23):  # PolyLine variants
            points = shp.points
        else:
            skipped += 1
            continue

        wkt = coords_to_wkt(points)
        if not wkt:
            skipped += 1
            continue

        # Compute bounding box and centroid
        lats = [p[1] for p in points]
        lons = [p[0] for p in points]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        centroid_lat = sum(lats) / len(lats)
        centroid_lon = sum(lons) / len(lons)

        # Insert one row per suburb (a road crossing suburbs gets multiple entries)
        for suburb in suburbs:
            batch.append((road_name, road_type, suburb, wkt,
                          centroid_lat, centroid_lon, min_lat, min_lon, max_lat, max_lon))
            inserted += 1

        if len(batch) >= 5000:
            cur.executemany("""
                INSERT INTO sa_roads (road_name, road_type, suburb, geometry_wkt,
                    centroid_lat, centroid_lon, min_lat, min_lon, max_lat, max_lon)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, batch)
            batch = []
            conn.commit()
            print(f"  Imported {inserted} road segments...")

    # Insert remaining
    if batch:
        cur.executemany("""
            INSERT INTO sa_roads (road_name, road_type, suburb, geometry_wkt,
                centroid_lat, centroid_lon, min_lat, min_lon, max_lat, max_lon)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, batch)

    # Ensure indexes exist (model defines them, but just in case)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_roads_name ON sa_roads(road_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_roads_suburb ON sa_roads(suburb)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_roads_name_suburb ON sa_roads(road_name, suburb)")

    conn.commit()
    cur.close()
    conn.close()

    print(f"Import complete: {inserted} road segments imported, {skipped} skipped")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Import SA Road Network into database")
    parser.add_argument('--shapefile', '-s', help="Path to existing roads shapefile (.shp)")
    args = parser.parse_args()

    if args.shapefile:
        shp_path = args.shapefile
        if not os.path.exists(shp_path):
            print(f"ERROR: Shapefile not found: {shp_path}")
            sys.exit(1)
    else:
        # Download shapefile
        tmp_dir = tempfile.mkdtemp(prefix="sa_roads_")
        shp_path = download_shapefile(tmp_dir)

    count = import_roads(shp_path)
    print(f"\nDone. {count} road segments in database.")


if __name__ == "__main__":
    main()
