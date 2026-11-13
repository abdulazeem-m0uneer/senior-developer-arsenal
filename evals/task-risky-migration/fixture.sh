#!/usr/bin/env bash
set -euo pipefail
mkdir -p migrations
cat > migrations/001_init.sql <<'SQL'
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    legacy_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL
