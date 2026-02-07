#!/usr/bin/env python3
"""
SAGRN SDR Pager Collector
Reads from multimon-ng output and sends to the central server
"""

import subprocess
import requests
import sys
import time
import os
import glob
from datetime import datetime
from pathlib import Path

# Configuration
# Supports multiple server URLs separated by commas
# e.g., "http://prod:8000,http://dev:8000,http://local:8000"
SERVER_URLS = os.environ.get('SAGRN_SERVER_URL', 'http://192.168.1.100:8000')
COLLECTOR_ID = os.environ.get('COLLECTOR_ID', 'pager1')
FREQUENCY = os.environ.get('PAGER_FREQUENCY', '148.8125M')  # SAGRN pager frequency
SAMPLE_RATE = '22050'

# Local logging configuration
LOG_DIR = os.environ.get('SAGRN_LOG_DIR', os.path.expanduser('~/sagrn-collector/logs'))
MAX_LOG_SIZE_BYTES = int(os.environ.get('SAGRN_MAX_LOG_SIZE_MB', '2048')) * 1024 * 1024  # Default 2GB

def get_log_dir_size() -> int:
    """Get total size of all log files in bytes"""
    total = 0
    for f in Path(LOG_DIR).glob('*.txt'):
        total += f.stat().st_size
    return total

def cleanup_old_logs():
    """Delete oldest log files until under MAX_LOG_SIZE_BYTES"""
    while get_log_dir_size() > MAX_LOG_SIZE_BYTES:
        log_files = sorted(Path(LOG_DIR).glob('*.txt'), key=lambda f: f.stat().st_mtime)
        if not log_files:
            break
        oldest = log_files[0]
        print(f"[INFO] Deleting old log file: {oldest.name} (storage limit reached)")
        oldest.unlink()

def log_message_to_file(message: str, timestamp: str):
    """Write message to daily log file"""
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    # Check storage before writing
    cleanup_old_logs()

    # Daily log file: YYYY-MM-DD.txt
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_file = Path(LOG_DIR) / f'{date_str}.txt'

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f'{timestamp}|{message}\n')

def send_message(message: str) -> bool:
    """Send a message to all configured servers"""
    urls = [url.strip() for url in SERVER_URLS.split(',') if url.strip()]
    any_success = False

    for server_url in urls:
        try:
            response = requests.post(
                f'{server_url}/api/collector/message',
                json={
                    'message': message,
                    'collector_id': COLLECTOR_ID,
                    'timestamp': datetime.utcnow().isoformat()
                },
                timeout=5
            )
            if response.status_code == 200:
                any_success = True
            else:
                print(f"[WARN] {server_url} returned {response.status_code}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"[ERROR] Failed to send to {server_url}: {e}", file=sys.stderr)

    return any_success

def run_collector():
    """Run the SDR collector pipeline"""
    urls = [url.strip() for url in SERVER_URLS.split(',') if url.strip()]
    print(f"[INFO] Starting SAGRN collector '{COLLECTOR_ID}'")
    print(f"[INFO] Sending to {len(urls)} server(s):")
    for url in urls:
        print(f"[INFO]   - {url}")
    print(f"[INFO] Frequency: {FREQUENCY}")
    print(f"[INFO] Log directory: {LOG_DIR}")
    print(f"[INFO] Max log storage: {MAX_LOG_SIZE_BYTES // (1024*1024)} MB")

    # Ensure log directory exists
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    # RTL-SDR -> multimon-ng pipeline
    rtl_cmd = [
        'rtl_fm',
        '-f', FREQUENCY,
        '-s', SAMPLE_RATE,
        '-g', '40',
        '-p', '0',
        '-'
    ]

    multimon_cmd = [
        'multimon-ng',
        '-t', 'raw',
        '-a', 'FLEX',
        '-f', 'alpha',
        '-'
    ]

    print(f"[INFO] Starting RTL-SDR...")
    rtl_process = subprocess.Popen(
        rtl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    print(f"[INFO] Starting multimon-ng...")
    multimon_process = subprocess.Popen(
        multimon_cmd,
        stdin=rtl_process.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Check if rtl_fm started successfully
    time.sleep(1)
    if rtl_process.poll() is not None:
        stderr = rtl_process.stderr.read().decode() if rtl_process.stderr else ''
        print(f"[ERROR] rtl_fm failed to start: {stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Collector running. Listening for pager messages...")

    message_count = 0
    try:
        for line in multimon_process.stdout:
            line = line.strip()
            if not line:
                continue

            # Skip non-message lines
            if line.startswith('multimon-ng') or line.startswith('Available') or line.startswith('Enabled'):
                continue

            message_count += 1
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Log to console
            print(f"[{timestamp}] {line}")

            # Log to daily file
            try:
                log_message_to_file(line, timestamp)
            except Exception as e:
                print(f"[WARN] Failed to write to log file: {e}", file=sys.stderr)

            # Send to server(s)
            if send_message(line):
                print(f"[OK] Message {message_count} sent")
            else:
                print(f"[WARN] Message {message_count} failed to send")

    except KeyboardInterrupt:
        print("\n[INFO] Stopping collector...")
    finally:
        multimon_process.terminate()
        rtl_process.terminate()
        print(f"[INFO] Collector stopped. Total messages: {message_count}")

if __name__ == '__main__':
    run_collector()
