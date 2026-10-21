#!/usr/bin/env bash
# Build → push (AgentBase Container Registry) → create/update Custom Agent runtime.
#
# Usage (Git Bash / Linux / macOS):
#   FLAVOR=2x4-general POC=true ./deploy.sh
#
# Biến môi trường:
#   RUNTIME_NAME   tên runtime                (mặc định: asr-system)
#   TAG            tag image                  (mặc định: vYYYYmmddHHMMSS)
#   FLAVOR         flavor compute (BẮT BUỘC)  xem: ./deploy.sh flavors
#   POC            true|false — ví POC hay ví thật (BẮT BUỘC khi tạo mới)
#                  kiểm tra: ./deploy.sh can-use-poc
#   PLATFORM       mặc định linux/amd64
#   MIN_REPLICAS / MAX_REPLICAS / CPU_SCALE / MEM_SCALE   (1 / 1 / 50 / 50)
#   ENV_FILE       env cho container          (mặc định: .env.deploy)
#
# Credentials GREENNODE_CLIENT_ID / GREENNODE_CLIENT_SECRET đọc từ ../.env
# (hoặc export sẵn trong shell).
set -euo pipefail

ASR_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$ASR_DIR/.." && pwd)"
SCRIPTS="$ROOT_DIR/.claude/skills/agentbase/scripts"
[ -d "$SCRIPTS" ] || SCRIPTS="$ROOT_DIR/greennode-agentbase-skills/skills/agentbase/scripts"

RUNTIME_NAME="${RUNTIME_NAME:-asr-system}"
TAG="${TAG:-v$(date +%Y%m%d%H%M%S)}"
PLATFORM="${PLATFORM:-linux/amd64}"
MIN_REPLICAS="${MIN_REPLICAS:-1}"
MAX_REPLICAS="${MAX_REPLICAS:-1}"
CPU_SCALE="${CPU_SCALE:-50}"
MEM_SCALE="${MEM_SCALE:-50}"
ENV_FILE="${ENV_FILE:-$ASR_DIR/.env.deploy}"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# --- Credentials -------------------------------------------------------------
if [ -z "${GREENNODE_CLIENT_ID:-}" ] && [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source <(tr -d '\r' < "$ROOT_DIR/.env" | grep -E '^GREENNODE_')
  set +a
fi
[ -n "${GREENNODE_CLIENT_ID:-}" ] && [ -n "${GREENNODE_CLIENT_SECRET:-}" ] \
  || die "Thiếu GREENNODE_CLIENT_ID / GREENNODE_CLIENT_SECRET (đặt trong $ROOT_DIR/.env)"

for bin in docker jq curl; do
  command -v "$bin" >/dev/null || die "Cần cài '$bin'"
done

runtime() { bash "$SCRIPTS/runtime.sh" "$@"; }
cr()      { bash "$SCRIPTS/cr.sh" "$@"; }

# --- Subcommands tiện ích ----------------------------------------------------
case "${1:-deploy}" in
  flavors)     runtime flavors; exit 0 ;;
  can-use-poc) bash "$SCRIPTS/billing.sh" can-use-poc; exit 0 ;;
  status)      runtime list --page 1 --size 100 \
                 | jq --arg n "$RUNTIME_NAME" '.listData[] | select(.name == $n)'; exit 0 ;;
  endpoint)    ;;
  deploy)      ;;
  *) die "Lệnh không hợp lệ: $1 (deploy | flavors | can-use-poc | status | endpoint)" ;;
esac

find_runtime_id() {
  local page=1 total=1 resp id
  while [ "$page" -le "$total" ]; do
    resp=$(runtime list --page "$page" --size 100)
    id=$(jq -r --arg n "$RUNTIME_NAME" '.listData[]? | select(.name == $n) | .id' <<<"$resp" | head -n1)
    [ -n "$id" ] && { echo "$id"; return; }
    total=$(jq -r '.totalPage // 1' <<<"$resp")
    page=$((page + 1))
  done
}

print_endpoint() {
  local rid="$1" url
  url=$(runtime endpoints list "$rid" \
    | jq -r '(.listData? // .) | if type == "array" then . else [.] end
             | map(select(.name == "DEFAULT"))[0].url // empty')
  [ -n "$url" ] || { echo "(chưa có URL endpoint — chạy lại: ./deploy.sh endpoint)"; return; }
  echo "Endpoint:  $url"
  echo "Health:    $(curl -s -o /dev/null -w '%{http_code}' "$url/health")"
  echo "Transcribe: POST $url/transcribe"
}

if [ "${1:-deploy}" = "endpoint" ]; then
  RID=$(find_runtime_id); [ -n "$RID" ] || die "Không tìm thấy runtime '$RUNTIME_NAME'"
  print_endpoint "$RID"; exit 0
fi

[ -n "${FLAVOR:-}" ] || die "Chưa đặt FLAVOR. Xem danh sách: ./deploy.sh flavors"
[ -f "$ENV_FILE" ]   || die "Không thấy env file: $ENV_FILE"

# --- 1. Container Registry ---------------------------------------------------
log "Lấy thông tin AgentBase Container Registry"
REPO_JSON=$(cr repo get)
REGISTRY=$(jq -r '.registryUrl' <<<"$REPO_JSON")
REPO=$(jq -r '.name' <<<"$REPO_JSON")
[ -n "$REGISTRY" ] && [ "$REGISTRY" != "null" ] || die "Không đọc được registryUrl: $REPO_JSON"
IMAGE="$REGISTRY/$REPO/$RUNTIME_NAME:$TAG"
echo "Image: $IMAGE"

log "Docker login"
cr credentials docker-login

# --- 2. Build & push ---------------------------------------------------------
log "Build image ($PLATFORM)"
docker build --platform "$PLATFORM" -t "$IMAGE" "$ASR_DIR"

log "Push image"
docker push "$IMAGE"

# --- 3. Create / update runtime ---------------------------------------------
COMMON_ARGS=(
  --image "$IMAGE"
  --flavor "$FLAVOR"
  --env-file "$ENV_FILE"
  --from-cr
  --min-replicas "$MIN_REPLICAS"
  --max-replicas "$MAX_REPLICAS"
  --cpu-scale "$CPU_SCALE"
  --mem-scale "$MEM_SCALE"
  --description "ASR: Zipformer STT (POST /transcribe)"
)

RID=$(find_runtime_id)
if [ -n "$RID" ]; then
  log "Cập nhật runtime $RUNTIME_NAME ($RID)"
  runtime update "$RID" "${COMMON_ARGS[@]}"
else
  [ -n "${POC:-}" ] || die "Tạo runtime mới cần POC=true|false (kiểm tra: ./deploy.sh can-use-poc)"
  log "Tạo runtime mới $RUNTIME_NAME"
  runtime create --name "$RUNTIME_NAME" --poc "$POC" "${COMMON_ARGS[@]}"
  RID=$(find_runtime_id)
fi

# --- 4. Kết quả --------------------------------------------------------------
log "Kết quả"
runtime get "$RID" | jq '{id, name, status, statusReason}'
print_endpoint "$RID"
echo "Console:   https://aiplatform.console.vngcloud.vn/agent-runtime?tab=runtime"
