#!/bin/sh
set -eu
# Runs only when the host PostgreSQL directory is empty.
# Passwords are read from private host files and never printed.
app_password=$(cat /run/private/app-password)
export GABBAPROC_INITIAL_APP_PASSWORD="$app_password"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_password GABBAPROC_INITIAL_APP_PASSWORD
CREATE ROLE gabbaproc_app LOGIN PASSWORD :'app_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO gabbaproc_app;
SQL
unset GABBAPROC_INITIAL_APP_PASSWORD app_password
