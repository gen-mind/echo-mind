#!/bin/bash
# Fix PostgreSQL password mismatch
#
# USE THIS WHEN: You see "password authentication failed for user echomind"
# in postgres logs, but your .env file has the correct password.
#
# ROOT CAUSE: POSTGRES_PASSWORD env var only works on FIRST initialization.
# If the volume already has data, changing the env var does nothing.
# You must sync the password inside postgres to match.

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Source the .env file to get POSTGRES_USER and POSTGRES_PASSWORD
source .env

echo "Syncing postgres password to match .env file..."
echo "User: $POSTGRES_USER"

# Run ALTER ROLE inside the postgres container
docker compose exec postgres psql -U "$POSTGRES_USER" -d postgres -c "ALTER ROLE $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';"

echo "Password synced. Recreating services that connect to postgres..."

# Stop and start services (--force-recreate alone doesn't always work)
docker compose stop api authentik-server authentik-worker
docker compose up -d api authentik-server authentik-worker

echo "Done! All services should now connect successfully."
echo ""
echo "Verify with: docker compose logs api --tail 10"
