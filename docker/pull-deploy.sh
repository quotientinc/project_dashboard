#!/usr/bin/env bash
# Pull-based deployment for Quotient Project Dashboard
#
# Pulls a pre-built image from GitHub Container Registry (GHCR) and deploys it.
# Use this instead of deploy.sh when images are built by GitHub Actions.
#
# Usage: pull-deploy.sh [tag]
#
# One-time setup on the server:
#   docker login ghcr.io
#   (use a GitHub personal access token with read:packages scope as the password)
#
# Example:
#   QPD_IMAGE=myorg/project_dashboard ./docker/pull-deploy.sh
#   QPD_IMAGE=myorg/project_dashboard ./docker/pull-deploy.sh abc1234
#
# Environment variables:
#   QPD_REGISTRY    - Container registry (default: ghcr.io)
#   QPD_IMAGE       - REQUIRED. Full image name, e.g. quotient-inc/project_dashboard
#   QPD_DEPLOY_DIR  - Deployment data directory (default: /var/www/vhosts/project-dashboard)
#   QPD_COMPOSE_FILE - Path to docker-compose.yml (default: auto-detect from script location)
set -euo pipefail

if [[ -z "${QPD_IMAGE:-}" ]]; then
    echo "ERROR: QPD_IMAGE is required. Set it to your GHCR image name." >&2
    echo "Example: QPD_IMAGE=myorg/project_dashboard $0" >&2
    exit 1
fi

readonly TAG="${1:-latest}"
readonly REGISTRY="${QPD_REGISTRY:-ghcr.io}"
readonly IMAGE="${QPD_IMAGE}"
readonly REMOTE_IMAGE="${REGISTRY}/${IMAGE}:${TAG}"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly COMPOSE_FILE="${QPD_COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"
readonly DEPLOY_DIR="${QPD_DEPLOY_DIR:-/var/www/vhosts/project-dashboard}"
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

# --- 1. Record current running container's image tag for rollback ---
PREVIOUS_TAG=$(docker compose -f "${COMPOSE_FILE}" images --format '{{.Tag}}' 2>/dev/null | head -1) || true
if [[ -n "${PREVIOUS_TAG}" ]]; then
    log "Previous image tag: ${TARGET_IMAGE}:${PREVIOUS_TAG}"
else
    log "No previous running container detected."
fi

trap rollback ERR

# --- 2. Pull image from GHCR ---
log "Pulling image ${REMOTE_IMAGE}"
docker pull "${REMOTE_IMAGE}"

# --- 3. Tag locally for compose compatibility ---
log "Tagging as ${TARGET_IMAGE}:${TAG}"
docker tag "${REMOTE_IMAGE}" "${TARGET_IMAGE}:${TAG}"

if [[ "${TAG}" != "latest" ]]; then
    docker tag "${REMOTE_IMAGE}" "${TARGET_IMAGE}:latest"
    log "Tagged ${TARGET_IMAGE}:latest"
fi

# --- 4. Ensure deploy data directory exists ---
mkdir -p "${DEPLOY_DIR}/data"
log "Deploy data directory ready: ${DEPLOY_DIR}/data"

# --- 5. Stop current containers and start new ones ---
log "Stopping current containers"
QPD_TAG="${TAG}" QPD_DATA_DIR="${DEPLOY_DIR}/data" \
    docker compose -f "${COMPOSE_FILE}" down

log "Starting containers with image ${TARGET_IMAGE}:${TAG}"
QPD_TAG="${TAG}" QPD_DATA_DIR="${DEPLOY_DIR}/data" \
    docker compose -f "${COMPOSE_FILE}" up -d

# --- 6. Health check loop ---
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

log "Deployment complete: ${TARGET_IMAGE}:${TAG} (pulled from ${REMOTE_IMAGE})"
