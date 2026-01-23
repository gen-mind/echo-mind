#!/bin/bash
# This script runs on every postgres container start
# It ensures the password in postgres matches POSTGRES_PASSWORD env var
# This fixes the issue where POSTGRES_PASSWORD only works on first init

set -e

# Wait for postgres to be ready
until pg_isready -U "$POSTGRES_USER" -d postgres; do
  echo "Waiting for postgres to be ready..."
  sleep 1
done

# Sync the password from environment variable to the database
# This ensures the password always matches what's in docker-compose/env
echo "Syncing postgres password from environment..."
psql -U "$POSTGRES_USER" -d postgres -c "ALTER ROLE $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';"
echo "Password synced successfully."
