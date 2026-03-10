#!/usr/bin/env bash
# Deploys the Quotient Project Dashboard
# Usage: deploy.sh [branch] [fastapi|streamlit]
#
# Environment variables:
#   QPD_REPO_DIR    - Path to the git repository (default: parent of this script's directory)
#   QPD_DEPLOY_DIR  - Path to the deployment directory (default: /var/www/vhosts/project-dashboard)
set -euo pipefail

readonly BRANCH="${1:-master}"
readonly APP_TYPE="${2:-fastapi}"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly REPO_DIR="${QPD_REPO_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
readonly DEPLOY_DIR="${QPD_DEPLOY_DIR:-/var/www/vhosts/project-dashboard}"
readonly COMPOSE_FILE="${REPO_DIR}/docker/docker-compose.yml"
readonly MAX_HEALTH_WAIT=60
readonly HEALTH_INTERVAL=2

case "${APP_TYPE}" in
    fastapi)
        readonly TARGET_IMAGE="qpd-fastapi"
        readonly COMPOSE_SERVICE="qpd-fastapi"
        readonly DOCKERFILE="${REPO_DIR}/docker/Dockerfile.fastapi"
        readonly HEALTH_URL="http://localhost:8000/api/health"
        ;;
    streamlit)
        readonly TARGET_IMAGE="qpd-streamlit"
        readonly COMPOSE_SERVICE="qpd-streamlit"
        readonly DOCKERFILE="${REPO_DIR}/docker/Dockerfile.streamlit"
        readonly HEALTH_URL="http://localhost:8501/_stcore/health"
        ;;
    *)
        echo "Usage: $0 [branch] [fastapi|streamlit]" >&2
        echo "  branch:   Git branch to deploy (default: master)" >&2
        echo "  App type: fastapi (default), streamlit" >&2
        exit 1
        ;;
esac

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
PREVIOUS_TAG=$(docker compose -f "${COMPOSE_FILE}" images "${COMPOSE_SERVICE}" --format '{{.Tag}}' 2>/dev/null | head -1) || true
if [[ -n "${PREVIOUS_TAG}" ]]; then
    log "Previous image tag: ${TARGET_IMAGE}:${PREVIOUS_TAG}"
else
    log "No previous running container detected."
fi

# --- 4. Build image with hash tag and latest tag ---
log "Building image ${TARGET_IMAGE}:${GIT_HASH}"
docker build \
    -f "${DOCKERFILE}" \
    -t "${TARGET_IMAGE}:${GIT_HASH}" \
    --label "git.head=${GIT_HASH}" \
    "${REPO_DIR}"

docker tag "${TARGET_IMAGE}:${GIT_HASH}" "${TARGET_IMAGE}:latest"
log "Tagged ${TARGET_IMAGE}:latest"

# --- 5. Ensure deploy directories exist ---
mkdir -p "${DEPLOY_DIR}/data" "${DEPLOY_DIR}/logs"
log "Deploy directories ready: ${DEPLOY_DIR}/{data,logs}"

# --- 6. Stop current container ---
log "Stopping current ${COMPOSE_SERVICE} container"
QPD_TAG="${GIT_HASH}" QPD_DATA_DIR="${DEPLOY_DIR}/data" QPD_LOG_DIR="${DEPLOY_DIR}/logs" \
    docker compose -f "${COMPOSE_FILE}" down "${COMPOSE_SERVICE}"

# --- 7. Start new container ---
log "Starting ${COMPOSE_SERVICE} with image ${TARGET_IMAGE}:${GIT_HASH}"
QPD_TAG="${GIT_HASH}" QPD_DATA_DIR="${DEPLOY_DIR}/data" QPD_LOG_DIR="${DEPLOY_DIR}/logs" \
    docker compose -f "${COMPOSE_FILE}" up -d "${COMPOSE_SERVICE}"

# --- 8. Health check loop ---
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
