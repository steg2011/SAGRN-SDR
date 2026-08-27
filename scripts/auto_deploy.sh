#!/usr/bin/env bash
#
# Pull-based auto-deploy for the NUC.
#
# GitHub Actions cannot reach this box: its only public ingress is the Cloudflare
# Tunnel, which carries HTTP, not SSH. So instead of CI pushing a deploy in, the
# NUC polls for new commits on main and deploys them itself. No inbound access, no
# GitHub secrets, and .env is never rewritten - it just stays on the host.
#
# Runs from cron as the user that owns the repo and is in the docker group.
# Install:  crontab -l | { cat; echo '*/5 * * * * /opt/sagrn-sdr/scripts/auto_deploy.sh'; } | crontab -
# Log:     /opt/sagrn-sdr/data/auto_deploy.log
#
# Exit codes: 0 nothing to do or deployed cleanly, 1 deploy failed.

set -uo pipefail

REPO="/opt/sagrn-sdr"
BRANCH="main"
API="https://api.github.com/repos/steg2011/SAGRN-SDR"
LOG="$REPO/data/auto_deploy.log"
LOCK="$REPO/data/auto_deploy.lock"
MAX_LOG_BYTES=$((5 * 1024 * 1024))

# Services to recreate on an ordinary deploy. The collector drives the RTL-SDR and
# is left alone unless its own code changed, so routine frontend/backend deploys
# never interrupt pager capture.
CORE_SERVICES="backend admin"
COLLECTOR_PATHS='^(collector\.Dockerfile|scripts/collector\.py)$'

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

cd "$REPO" || exit 1
mkdir -p "$(dirname "$LOG")"

# Keep the log from growing without bound
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt "$MAX_LOG_BYTES" ]; then
  tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

# Never let two deploys overlap - a build easily outruns the cron interval
exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0
fi

if ! git fetch --quiet origin "$BRANCH" 2>>"$LOG"; then
  log "fetch failed, will retry next run"
  exit 0
fi

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

[ "$LOCAL" = "$REMOTE" ] && exit 0

# Refuse to deploy over local edits rather than clobbering someone's work
if ! git diff --quiet || ! git diff --cached --quiet; then
  log "SKIP ${REMOTE:0:7}: working tree is dirty, resolve by hand"
  exit 0
fi

# Only deploy a commit whose CI actually passed. Public repo, so no token needed;
# if the check is unreachable or still running, hold off and retry next run.
CONCLUSION="$(curl -sf --max-time 20 "$API/commits/$REMOTE/check-runs" 2>/dev/null |
  python3 -c "
import json,sys
try: runs = json.load(sys.stdin).get('check_runs', [])
except Exception: print('unknown'); raise SystemExit
run = next((r for r in runs if r['name'] == 'lint-and-test'), None)
print('none' if run is None else (run['conclusion'] or 'running'))
" 2>/dev/null)"

case "${CONCLUSION:-unknown}" in
  success) ;;
  running|none|unknown)
    log "WAIT ${REMOTE:0:7}: CI is ${CONCLUSION:-unknown}"
    exit 0 ;;
  *)
    log "SKIP ${REMOTE:0:7}: CI concluded $CONCLUSION"
    exit 0 ;;
esac

log "DEPLOY ${LOCAL:0:7} -> ${REMOTE:0:7}"

if ! git merge --ff-only --quiet "origin/$BRANCH" >>"$LOG" 2>&1; then
  log "FAIL: fast-forward refused, local history has diverged"
  exit 1
fi

SERVICES="$CORE_SERVICES"
if git diff --name-only "$LOCAL" "$REMOTE" | grep -qE "$COLLECTOR_PATHS"; then
  SERVICES="$SERVICES collector"
  log "collector code changed, including it in this deploy"
fi

if ! docker compose up -d --build $SERVICES >>"$LOG" 2>&1; then
  log "FAIL: docker compose up failed, rolling back to ${LOCAL:0:7}"
  git reset --hard --quiet "$LOCAL"
  docker compose up -d $SERVICES >>"$LOG" 2>&1
  exit 1
fi

docker image prune -f >/dev/null 2>&1

# A container that exits right after start would otherwise look like success
sleep 10
if ! curl -sf --max-time 10 http://127.0.0.1:8000/api/health >/dev/null; then
  log "FAIL: backend unhealthy after deploy, rolling back to ${LOCAL:0:7}"
  git reset --hard --quiet "$LOCAL"
  docker compose up -d --build $SERVICES >>"$LOG" 2>&1
  exit 1
fi

log "OK ${REMOTE:0:7} deployed ($SERVICES)"
