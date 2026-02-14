#!/usr/bin/env python3
"""
Import G-NAF (Geocoded National Address File) SA addresses into the PostgreSQL database.

Downloads the G-NAF flat file from data.gov.au, filters to South Australia only,
and imports address points into the sa_addresses table for local geocoding.

Usage:
    python scripts/import_gnaf.py [--gnaf-zip PATH]
"""

import argparse
import csv
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import psycopg2


# G-NAF data.gov.au dataset page
GNAF_DATASET_URL = "https://data.gov.au/data/api/3/action/package_show"
GNAF_DATASET_ID = "geocoded-national-address-file-g-naf"

# SA state abbreviation in G-NAF
SA_STATE = "SA"
SA_STATE_PID_PREFIX = "4"  # SA state PID prefix in G-NAF

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://sagrn:password@localhost:5432/sagrn'
)


def get_pg_dsn():
    """Convert async DATABASE_URL to sync psycopg2 DSN."""
    url = DATABASE_URL
    url = url.replace('postgresql+asyncpg://', 'postgresql://')
    url = url.replace('postgres+asyncpg://', 'postgresql://')
    return url


def download_gnaf(output_dir):
    """Download the G-NAF flat file from data.gov.au."""
    print("Fetching G-NAF download URL from data.gov.au...")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        # Try the CKAN API to find the flat file resource
        resp = client.get(GNAF_DATASET_URL, params={"id": GNAF_DATASET_ID})

        download_url = None
        if resp.status_code == 200:
            data = resp.json()
            resources = data.get('result', {}).get('resources', [])

            # Look for the GDA2020 flat file or any flat file
            for resource in resources:
                name = resource.get('name', '').lower()
                url = resource.get('url', '')
                if 'gda2020' in name and ('flat' in name or '.zip' in url.lower()):
                    download_url = url
                    break

            # Fallback: any zip file
            if not download_url:
                for resource in resources:
                    url = resource.get('url', '')
                    if url.lower().endswith('.zip'):
                        download_url = url
                        break

        if not download_url:
            print("ERROR: Could not determine G-NAF download URL.")
            print("Please download the G-NAF data manually from:")
            print("  https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf")
            print(f"  and provide the path with --gnaf-zip")
            sys.exit(1)

        print(f"Downloading G-NAF from: {download_url}")
        print("(This is a large file ~1.5GB, please wait...)")

        zip_path = os.path.join(output_dir, "gnaf.zip")
        with client.stream("GET", download_url) as response:
            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and downloaded % (10 * 1024 * 1024) == 0:
                        pct = downloaded / total * 100
                        print(f"  Downloaded {downloaded / 1024 / 1024:.0f}MB / {total / 1024 / 1024:.0f}MB ({pct:.0f}%)")

    print(f"Downloaded to {zip_path}")
    return zip_path


def find_address_files(zip_path):
    """Find the relevant SA address PSV files within the G-NAF zip."""
    files = {}

    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            # Get just the filename (not path)
            basename = os.path.basename(name).upper()

            # Only process SA-specific files (filenames start with SA_)
            if not basename.startswith('SA_'):
                # Also check for flat file format
                if 'GNAF_FLAT' in basename and basename.endswith('.CSV'):
                    files['flat'] = name
                continue

            if 'ADDRESS_DEFAULT_GEOCODE' in basename and basename.endswith('.PSV'):
                files['geocode'] = name
            elif 'ADDRESS_DETAIL' in basename and basename.endswith('.PSV'):
                files['detail'] = name
            elif 'STREET_LOCALITY' in basename and basename.endswith('.PSV'):
                files['street'] = name
            elif 'LOCALITY' in basename and 'STREET' not in basename and basename.endswith('.PSV'):
                files['locality'] = name

    return files


def import_gnaf_flat(zip_path):
    """Import G-NAF flat file format (simpler, single CSV with all fields)."""
    print("Looking for G-NAF flat file format...")

    conn = psycopg2.connect(get_pg_dsn())
    cur = conn.cursor()

    # Truncate existing data
    cur.execute("TRUNCATE TABLE sa_addresses RESTART IDENTITY")
    conn.commit()

    inserted = 0

    with zipfile.ZipFile(zip_path) as zf:
        # Find the flat file — must contain 'FLAT' in name
        flat_file = None
        for name in zf.namelist():
            basename = os.path.basename(name).upper()
            if 'FLAT' in basename and (basename.endswith('.CSV') or basename.endswith('.PSV')):
                flat_file = name
                break

        if not flat_file:
            print("ERROR: No CSV/PSV file found in the G-NAF archive")
            conn.close()
            return 0

        print(f"Processing: {flat_file}")

        with zf.open(flat_file) as f:
            # Detect delimiter
            text_io = io.TextIOWrapper(f, encoding='utf-8', errors='replace')
            first_line = text_io.readline()

            if '|' in first_line:
                delimiter = '|'
            else:
                delimiter = ','

            # Parse header
            headers = [h.strip().upper() for h in first_line.split(delimiter)]
            print(f"  Headers: {headers[:10]}...")

            # Map column indices
            col_map = {h: i for i, h in enumerate(headers)}

            # Find relevant columns (G-NAF flat file column names)
            num_col = None
            name_col = None
            type_col = None
            suburb_col = None
            postcode_col = None
            lat_col = None
            lon_col = None
            state_col = None

            for candidates, target in [
                (['NUMBER_FIRST', 'STREET_NUMBER_1', 'HOUSE_NUMBER_1', 'ADDRESS_SITE_NAME'], 'num'),
                (['STREET_NAME', 'STREET_NM'], 'name'),
                (['STREET_TYPE_CODE', 'STREET_TYPE', 'STREET_TP'], 'type'),
                (['LOCALITY_NAME', 'SUBURB', 'LOCALITY'], 'suburb'),
                (['POSTCODE', 'POST_CODE'], 'postcode'),
                (['LATITUDE', 'LAT'], 'lat'),
                (['LONGITUDE', 'LON', 'LNG', 'LONG'], 'lon'),
                (['STATE_ABBREVIATION', 'STATE', 'STATE_AB'], 'state'),
            ]:
                for c in candidates:
                    if c in col_map:
                        if target == 'num': num_col = col_map[c]
                        elif target == 'name': name_col = col_map[c]
                        elif target == 'type': type_col = col_map[c]
                        elif target == 'suburb': suburb_col = col_map[c]
                        elif target == 'postcode': postcode_col = col_map[c]
                        elif target == 'lat': lat_col = col_map[c]
                        elif target == 'lon': lon_col = col_map[c]
                        elif target == 'state': state_col = col_map[c]
                        break

            if name_col is None or lat_col is None or lon_col is None:
                print(f"  ERROR: Missing required columns. Found: {col_map}")
                conn.close()
                return 0

            print(f"  Column mapping - num:{num_col}, name:{name_col}, type:{type_col}, "
                  f"suburb:{suburb_col}, postcode:{postcode_col}, lat:{lat_col}, lon:{lon_col}, state:{state_col}")

            # Process rows
            batch = []
            for line in text_io:
                parts = line.strip().split(delimiter)
                max_col = max(c for c in [num_col, name_col, type_col, suburb_col,
                                          postcode_col, lat_col, lon_col, state_col] if c is not None)
                if len(parts) <= max_col:
                    continue

                # Filter to SA only
                if state_col is not None:
                    state = parts[state_col].strip().upper()
                    if state != 'SA' and state != 'SOUTH AUSTRALIA':
                        continue

                try:
                    lat = float(parts[lat_col].strip())
                    lon = float(parts[lon_col].strip())
                except (ValueError, IndexError):
                    continue

                # SA bounding box check (rough filter)
                if not (-38.1 <= lat <= -25.9 and 128.9 <= lon <= 141.1):
                    continue

                street_name = parts[name_col].strip().upper() if name_col is not None else ''
                if not street_name:
                    continue

                street_number = parts[num_col].strip() if num_col is not None else None
                street_type = parts[type_col].strip().upper() if type_col is not None else None
                suburb = parts[suburb_col].strip().upper() if suburb_col is not None else None
                postcode = parts[postcode_col].strip() if postcode_col is not None else None

                batch.append((street_number, street_name, street_type, suburb, postcode, lat, lon))

                if len(batch) >= 5000:
                    cur.executemany("""
                        INSERT INTO sa_addresses (street_number, street_name, street_type,
                            suburb, postcode, latitude, longitude)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, batch)
                    inserted += len(batch)
                    batch = []
                    if inserted % 50000 == 0:
                        print(f"  Imported {inserted} addresses...")
                        conn.commit()

            # Insert remaining
            if batch:
                cur.executemany("""
                    INSERT INTO sa_addresses (street_number, street_name, street_type,
                        suburb, postcode, latitude, longitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, batch)
                inserted += len(batch)

    # Create indexes
    print("Creating indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_name ON sa_addresses(street_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_suburb ON sa_addresses(suburb)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_name_suburb ON sa_addresses(street_name, suburb)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_number ON sa_addresses(street_number)")

    conn.commit()
    cur.close()
    conn.close()

    return inserted


def import_gnaf_standard(zip_path):
    """Import G-NAF standard format (multiple PSV files that need joining)."""
    print("Processing G-NAF standard format (multi-file join)...")

    files = find_address_files(zip_path)
    print(f"Found files: {list(files.keys())}")

    if 'flat' in files:
        return import_gnaf_flat(zip_path)

    if not files.get('detail') or not files.get('geocode'):
        print("ERROR: Required G-NAF files not found in archive.")
        print("Need ADDRESS_DETAIL and ADDRESS_DEFAULT_GEOCODE files.")
        return 0

    # For standard format, we load into temp tables then join
    conn = psycopg2.connect(get_pg_dsn())
    cur = conn.cursor()

    # Truncate target table
    cur.execute("TRUNCATE TABLE sa_addresses RESTART IDENTITY")
    conn.commit()

    # Create temp tables for joining
    cur.execute("CREATE TEMP TABLE tmp_geocode (address_detail_pid TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION)")
    cur.execute("CREATE TEMP TABLE tmp_detail (address_detail_pid TEXT, street_locality_pid TEXT, "
                "number_first TEXT, postcode TEXT, locality_pid TEXT)")
    cur.execute("CREATE TEMP TABLE tmp_street (street_locality_pid TEXT, street_name TEXT, "
                "street_type TEXT, locality_pid TEXT)")
    cur.execute("CREATE TEMP TABLE tmp_locality (locality_pid TEXT, locality_name TEXT)")
    conn.commit()

    with zipfile.ZipFile(zip_path) as zf:
        # Load geocode data
        if 'geocode' in files:
            print(f"  Loading geocodes: {files['geocode']}")
            with zf.open(files['geocode']) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='|')
                headers = [h.strip().upper() for h in next(reader)]
                pid_idx = headers.index('ADDRESS_DETAIL_PID') if 'ADDRESS_DETAIL_PID' in headers else 0
                lat_idx = headers.index('LATITUDE') if 'LATITUDE' in headers else None
                lon_idx = headers.index('LONGITUDE') if 'LONGITUDE' in headers else None

                if lat_idx is not None and lon_idx is not None:
                    batch = []
                    for row in reader:
                        try:
                            lat = float(row[lat_idx])
                            lon = float(row[lon_idx])
                            if -38.1 <= lat <= -25.9 and 128.9 <= lon <= 141.1:
                                batch.append((row[pid_idx], lat, lon))
                        except (ValueError, IndexError):
                            continue
                        if len(batch) >= 5000:
                            cur.executemany("INSERT INTO tmp_geocode VALUES (%s, %s, %s)", batch)
                            batch = []
                    if batch:
                        cur.executemany("INSERT INTO tmp_geocode VALUES (%s, %s, %s)", batch)
                    conn.commit()

        # Load address details
        if 'detail' in files:
            print(f"  Loading address details: {files['detail']}")
            with zf.open(files['detail']) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='|')
                headers = [h.strip().upper() for h in next(reader)]
                col = {h: i for i, h in enumerate(headers)}
                batch = []
                for row in reader:
                    try:
                        pid = row[col.get('ADDRESS_DETAIL_PID', 0)]
                        slp = row[col.get('STREET_LOCALITY_PID', 1)] if 'STREET_LOCALITY_PID' in col else ''
                        num = row[col.get('NUMBER_FIRST', 2)] if 'NUMBER_FIRST' in col else ''
                        pc = row[col.get('POSTCODE', 3)] if 'POSTCODE' in col else ''
                        lp = row[col.get('LOCALITY_PID', 4)] if 'LOCALITY_PID' in col else ''
                        batch.append((pid, slp, num, pc, lp))
                    except IndexError:
                        continue
                    if len(batch) >= 5000:
                        cur.executemany("INSERT INTO tmp_detail VALUES (%s, %s, %s, %s, %s)", batch)
                        batch = []
                if batch:
                    cur.executemany("INSERT INTO tmp_detail VALUES (%s, %s, %s, %s, %s)", batch)
                conn.commit()

        # Load street locality
        if 'street' in files:
            print(f"  Loading streets: {files['street']}")
            with zf.open(files['street']) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='|')
                headers = [h.strip().upper() for h in next(reader)]
                col = {h: i for i, h in enumerate(headers)}
                batch = []
                for row in reader:
                    try:
                        slp = row[col.get('STREET_LOCALITY_PID', 0)]
                        sn = row[col.get('STREET_NAME', 1)] if 'STREET_NAME' in col else ''
                        st = row[col.get('STREET_TYPE_CODE', 2)] if 'STREET_TYPE_CODE' in col else ''
                        lp = row[col.get('LOCALITY_PID', 3)] if 'LOCALITY_PID' in col else ''
                        batch.append((slp, sn.upper(), st.upper(), lp))
                    except IndexError:
                        continue
                    if len(batch) >= 5000:
                        cur.executemany("INSERT INTO tmp_street VALUES (%s, %s, %s, %s)", batch)
                        batch = []
                if batch:
                    cur.executemany("INSERT INTO tmp_street VALUES (%s, %s, %s, %s)", batch)
                conn.commit()

        # Load localities
        if 'locality' in files:
            print(f"  Loading localities: {files['locality']}")
            with zf.open(files['locality']) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='|')
                headers = [h.strip().upper() for h in next(reader)]
                col = {h: i for i, h in enumerate(headers)}
                batch = []
                for row in reader:
                    try:
                        lp = row[col.get('LOCALITY_PID', 0)]
                        ln = row[col.get('LOCALITY_NAME', 1)] if 'LOCALITY_NAME' in col else ''
                        batch.append((lp, ln.upper()))
                    except IndexError:
                        continue
                    if len(batch) >= 5000:
                        cur.executemany("INSERT INTO tmp_locality VALUES (%s, %s)", batch)
                        batch = []
                if batch:
                    cur.executemany("INSERT INTO tmp_locality VALUES (%s, %s)", batch)
                conn.commit()

    # Join tables into sa_addresses
    print("Joining tables...")
    cur.execute("CREATE INDEX tmp_geocode_pid ON tmp_geocode(address_detail_pid)")
    cur.execute("CREATE INDEX tmp_detail_pid ON tmp_detail(address_detail_pid)")
    cur.execute("CREATE INDEX tmp_detail_slp ON tmp_detail(street_locality_pid)")
    cur.execute("CREATE INDEX tmp_street_slp ON tmp_street(street_locality_pid)")
    cur.execute("CREATE INDEX tmp_locality_lp ON tmp_locality(locality_pid)")

    cur.execute("""
        INSERT INTO sa_addresses (street_number, street_name, street_type, suburb, postcode, latitude, longitude)
        SELECT d.number_first, s.street_name, s.street_type, l.locality_name, d.postcode, g.latitude, g.longitude
        FROM tmp_geocode g
        JOIN tmp_detail d ON d.address_detail_pid = g.address_detail_pid
        JOIN tmp_street s ON s.street_locality_pid = d.street_locality_pid
        LEFT JOIN tmp_locality l ON l.locality_pid = d.locality_pid
        WHERE s.street_name != ''
    """)
    inserted = cur.rowcount

    # Create indexes
    print("Creating indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_name ON sa_addresses(street_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_suburb ON sa_addresses(suburb)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_name_suburb ON sa_addresses(street_name, suburb)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sa_addresses_number ON sa_addresses(street_number)")

    # Cleanup temp tables
    cur.execute("DROP TABLE tmp_geocode")
    cur.execute("DROP TABLE tmp_detail")
    cur.execute("DROP TABLE tmp_street")
    cur.execute("DROP TABLE tmp_locality")

    conn.commit()
    cur.close()
    conn.close()

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Import G-NAF SA addresses into database")
    parser.add_argument('--gnaf-zip', '-g', help="Path to existing G-NAF zip file")
    args = parser.parse_args()

    if args.gnaf_zip:
        zip_path = args.gnaf_zip
        if not os.path.exists(zip_path):
            print(f"ERROR: File not found: {zip_path}")
            sys.exit(1)
    else:
        tmp_dir = tempfile.mkdtemp(prefix="gnaf_")
        zip_path = download_gnaf(tmp_dir)

    # Try standard format first (multi-file join), fall back to flat file
    count = import_gnaf_standard(zip_path)
    if count == 0:
        count = import_gnaf_flat(zip_path)

    print(f"\nDone. {count} SA addresses in database.")


if __name__ == "__main__":
    main()
