-- Run this against your EXISTING ai_sdlc database to add
-- login rate-limiting/lockout support.
--
--   mysql -u root -p ai_sdlc < migration_add_login_lockout.sql

USE ai_sdlc;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS failed_login_attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until DATETIME NULL;
