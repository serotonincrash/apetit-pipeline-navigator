#!/usr/bin/env bash
# Set up or remove a worktree with its own databases and buckets in the shared dev services.
#
#   scripts/worktree.sh up <name> <slot>   new worktree in .worktrees/<name> on branch <name>
#   scripts/worktree.sh down <name>        drop its databases and buckets, remove the worktree
#
# Needs the shared services running: docker compose -f infra/docker-compose.yml --profile dev up -d
# and the seed bucket filled once per computer (see README).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PG_URL="${PG_ADMIN_URL:-postgresql://navigator:navigator@localhost:5432/postgres}"
cmd="${1:-}"
name="${2:-}"
[[ -n "$cmd" && -n "$name" ]] || { sed -n '2,8p' "$0"; exit 1; }
db="navigator_${name//-/_}"
bucket="navigator-${name//_/-}"
tree="$ROOT/.worktrees/$name"

case "$cmd" in
up)
  slot="${3:?slot number required}"
  git -C "$ROOT" worktree add "$tree" -b "$name"
  psql "$PG_URL" -qc "CREATE DATABASE $db" -c "CREATE DATABASE ${db}_test"
  cat > "$tree/backend/.env" <<EOF
DATABASE_URL=postgresql+psycopg://navigator:navigator@localhost:5432/$db
TEST_DATABASE_URL=postgresql+psycopg://navigator:navigator@localhost:5432/${db}_test
S3_ENDPOINT=localhost:8333
S3_BUCKET=$bucket
TEST_S3_BUCKET=$bucket-test
S3_SEED_BUCKET=navigator-seed
S3_ACCESS_KEY=navigator
S3_SECRET_KEY=navigator-dev
PACKAGE_DIR=$ROOT/APETIT_CLIMATE_NATURE_NAVIGATOR_2026
API_PORT=$((8100 + slot))
WEB_PORT=$((5200 + slot))
EOF
  cd "$tree/backend"
  uv sync
  uv run alembic upgrade head
  uv run python -m navigator.seed --from-bucket navigator-seed
  echo "Worktree $name ready: API port $((8100 + slot)), database $db, bucket $bucket"
  ;;
down)
  (cd "$tree/backend" && uv run python -c "
from navigator.storage import objects
c = objects.get_client()
for b in ['$bucket', '$bucket-test']:
    if c.bucket_exists(b):
        for o in c.list_objects(b, recursive=True):
            c.remove_object(b, o.object_name)
        c.remove_bucket(b)
") || true
  psql "$PG_URL" -qc "DROP DATABASE IF EXISTS $db" -c "DROP DATABASE IF EXISTS ${db}_test"
  git -C "$ROOT" worktree remove "$tree"
  ;;
*)
  sed -n '2,8p' "$0"; exit 1 ;;
esac
