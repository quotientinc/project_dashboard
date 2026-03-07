#!/usr/bin/env bash
# Deploys the Quotient Project Dashboard
# Usage: deploy.sh [branch]
#
# Environment variables:
#   QPD_REPO_DIR    - Path to the git repository (default: parent of this script's directory)
#   QPD_DEPLOY_DIR  - Path to the deployment directory (default: /var/www/vhosts/project-dashboard)
set -euo pipefail

readonly BRANCH="${1:-master}"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly REPO_DIR="${QPD_REPO_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
readonly DEPLOY_DIR="${QPD_DEPLOY_DIR:-/var/www/vhosts/project-dashboard}"
readonly COMPOSE_FILE="${REPO_DIR}/docker/docker-compose.yml"
readonly TARGET_IMAGE="qpd"
readonly MAX_HEALTH_WAIT=60
readonly HEALTH_INTERVAL=2

PREVIOUS_TAG=""

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

rollback() {
    log "ERROR: Deployment failed!"
    if [[ -n "${PREVIOUS_TAG}" ]]; then
        log "Attempting rollback to previous image: ${TARGET_IMAGE}:${PREVIOUS_TAG}"
        QPD_TAG="${PREVIOUS_TAG}" QPD_DATA_DIR="${DEPLOY_DIR}/data" \
            docker compose -f "${COMPOSE_FILE}" up -d
        log "Rollback complete. Previous version restored."
    else
        log "No previous image tag recorded. Manual intervention required."
    fi
    exit 1
}

trap rollback ERR

# --- 1. Update repository ---
log "Fetching and checking out branch '${BRANCH}' in ${REPO_DIR}"
cd "${REPO_DIR}"
git fetch --all --prune
git checkout "${BRANCH}"
git pull origin "${BRANCH}"

# --- 2. Get git short hash for tagging ---
readonly GIT_HASH="$(git rev-parse --short HEAD)"
log "Git hash: ${GIT_HASH}"

# --- 3. Record current running container's image tag for rollback ---
PREVIOUS_TAG=$(docker compose -f "${COMPOSE_FILE}" images --format '{{.Tag}}' 2>/dev/null | head -1) || true
if [[ -n "${PREVIOUS_TAG}" ]]; then
    log "Previous image tag: ${TARGET_IMAGE}:${PREVIOUS_TAG}"
else
    log "No previous running container detected."
fi

# --- 4. Build image with hash tag and latest tag ---
log "Building image ${TARGET_IMAGE}:${GIT_HASH}"
docker build \
    -f "${REPO_DIR}/docker/Dockerfile" \
    -t "${TARGET_IMAGE}:${GIT_HASH}" \
    --label "git.head=${GIT_HASH}" \
    "${REPO_DIR}"

docker tag "${TARGET_IMAGE}:${GIT_HASH}" "${TARGET_IMAGE}:latest"
log "Tagged ${TARGET_IMAGE}:latest"

# --- 5. Ensure deploy data directory exists ---
mkdir -p "${DEPLOY_DIR}/data"
log "Deploy data directory ready: ${DEPLOY_DIR}/data"

# --- 6. Stop current containers ---
log "Stopping current containers"
QPD_TAG="${GIT_HASH}" QPD_DATA_DIR="${DEPLOY_DIR}/data" \
    docker compose -f "${COMPOSE_FILE}" down

# --- 7. Start new containers ---
log "Starting containers with image ${TARGET_IMAGE}:${GIT_HASH}"
QPD_TAG="${GIT_HASH}" QPD_DATA_DIR="${DEPLOY_DIR}/data" \
    docker compose -f "${COMPOSE_FILE}" up -d

# --- 8. Health check loop ---
log "Waiting for health check (up to ${MAX_HEALTH_WAIT}s)..."
elapsed=0
while (( elapsed < MAX_HEALTH_WAIT )); do
    if curl --silent --fail http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        log "Health check passed after ${elapsed}s"
        break
    fi
    sleep "${HEALTH_INTERVAL}"
    elapsed=$(( elapsed + HEALTH_INTERVAL ))
done

if (( elapsed >= MAX_HEALTH_WAIT )); then
    log "Health check failed after ${MAX_HEALTH_WAIT}s"
    exit 1
fi

# --- 9. Prune old images, keep last 5 tagged versions ---
log "Pruning old images (keeping last 5 tagged versions)"
docker images "${TARGET_IMAGE}" --format '{{.Tag}} {{.CreatedAt}}' \
    | grep -v '<none>' \
    | grep -v 'latest' \
    | sort -k2 -r \
    | tail -n +6 \
    | awk '{print $1}' \
    | while read -r old_tag; do
        log "Removing old image: ${TARGET_IMAGE}:${old_tag}"
        docker rmi "${TARGET_IMAGE}:${old_tag}" 2>/dev/null || true
    done

log "Deployment complete: ${TARGET_IMAGE}:${GIT_HASH} (branch: ${BRANCH})"
