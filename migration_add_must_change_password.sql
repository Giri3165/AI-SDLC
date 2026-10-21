-- Run this against your EXISTING ai_sdlc database to add
-- the forced first-login password-change flow.
--
--   mysql -u root -p ai_sdlc < migration_add_must_change_password.sql

USE ai_sdlc;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;
