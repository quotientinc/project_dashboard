#!/usr/bin/env bash
# Pull-based deployment for Quotient Project Dashboard
#
# Pulls a pre-built image from GitHub Container Registry (GHCR) and deploys it.
# Use this instead of deploy.sh when images are built by GitHub Actions.
#
# Usage: pull-deploy.sh [fastapi|streamlit] [tag]
#
#   First argument:  app type (default: fastapi)
#   Second argument: image tag (default: latest)
#
# One-time setup on the server:
#   docker login ghcr.io
#   (use a GitHub personal access token with read:packages scope as the password)
#
# Example:
#   QPD_IMAGE=myorg/project_dashboard ./docker/pull-deploy.sh
#   QPD_IMAGE=myorg/project_dashboard ./docker/pull-deploy.sh fastapi abc1234
#   QPD_IMAGE=myorg/project_dashboard ./docker/pull-deploy.sh streamlit latest
#
# Environment variables:
#   QPD_REGISTRY    - Container registry (default: ghcr.io)
#   QPD_IMAGE       - REQUIRED. Full image name, e.g. quotient-inc/project_dashboard
#   QPD_DEPLOY_DIR  - Deployment data directory (default: /var/www/vhosts/project-dashboard)
#   QPD_COMPOSE_FILE - Path to docker-compose.yml (default: auto-detect from script location)
set -euo pipefail

if [[ -z "${QPD_IMAGE:-}" ]]; then
    echo "ERROR: QPD_IMAGE is required. Set it to your GHCR image name." >&2
    echo "Example: QPD_IMAGE=myorg/project_dashboard $0 [fastapi|streamlit] [tag]" >&2
    exit 1
fi

# --- Parse app type argument ---
readonly APP_TYPE="${1:-fastapi}"

case "${APP_TYPE}" in
    fastapi)
        TARGET_IMAGE="qpd-fastapi"
        HEALTH_URL="http://localhost:8000/api/health"
        COMPOSE_SERVICE="qpd-fastapi"
        IMAGE_SUFFIX="-fastapi"
        ;;
    streamlit)
        TARGET_IMAGE="qpd-streamlit"
        HEALTH_URL="http://localhost:8501/_stcore/health"
        COMPOSE_SERVICE="qpd-streamlit"
        IMAGE_SUFFIX="-streamlit"
        ;;
    *)
        echo "ERROR: Invalid app type '${APP_TYPE}'. Must be 'fastapi' or 'streamlit'." >&2
        echo "Usage: $0 [fastapi|streamlit] [tag]" >&2
        exit 1
        ;;
esac

readonly TARGET_IMAGE
readonly HEALTH_URL
readonly COMPOSE_SERVICE
readonly IMAGE_SUFFIX

readonly TAG="${2:-latest}"
readonly REGISTRY="${QPD_REGISTRY:-ghcr.io}"
readonly IMAGE="${QPD_IMAGE}${IMAGE_SUFFIX}"
readonly REMOTE_IMAGE="${REGISTRY}/${IMAGE}:${TAG}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly SCRIPT_DIR
readonly COMPOSE_FILE="${QPD_COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"
readonly DEPLOY_DIR="${QPD_DEPLOY_DIR:-/var/www/vhosts/project-dashboard}"
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
        QPD_TAG="${PREVIOUS_TAG}" QPD_DATA_DIR="${DEPLOY_DIR}/data" QPD_LOG_DIR="${DEPLOY_DIR}/logs" \
            docker compose -f "${COMPOSE_FILE}" up -d "${COMPOSE_SERVICE}"
        log "Rollback complete. Previous version restored."
    else
        log "No previous image tag recorded. Manual intervention required."
    fi
    exit 1
}

# --- 1. Record current running container's image tag for rollback ---
PREVIOUS_TAG=$(docker compose -f "${COMPOSE_FILE}" images "${COMPOSE_SERVICE}" --format '{{.Tag}}' 2>/dev/null | head -1) || true
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

# --- 4. Ensure deploy directories exist ---
mkdir -p "${DEPLOY_DIR}/data" "${DEPLOY_DIR}/logs"
log "Deploy directories ready: ${DEPLOY_DIR}/{data,logs}"

# --- 5. Stop current container and start new one ---
log "Stopping current ${COMPOSE_SERVICE} container"
QPD_TAG="${TAG}" QPD_DATA_DIR="${DEPLOY_DIR}/data" QPD_LOG_DIR="${DEPLOY_DIR}/logs" \
    docker compose -f "${COMPOSE_FILE}" down "${COMPOSE_SERVICE}"

log "Starting ${COMPOSE_SERVICE} with image ${TARGET_IMAGE}:${TAG}"
QPD_TAG="${TAG}" QPD_DATA_DIR="${DEPLOY_DIR}/data" QPD_LOG_DIR="${DEPLOY_DIR}/logs" \
    docker compose -f "${COMPOSE_FILE}" up -d "${COMPOSE_SERVICE}"

# --- 6. Health check loop ---
log "Waiting for health check at ${HEALTH_URL} (up to ${MAX_HEALTH_WAIT}s)..."
elapsed=0
while (( elapsed < MAX_HEALTH_WAIT )); do
    if curl --silent --fail "${HEALTH_URL}" > /dev/null 2>&1; then
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
