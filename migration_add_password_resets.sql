-- Run this against your EXISTING ai_sdlc database to add
-- password-reset support without touching anything else.
--
--   mysql -u root -p ai_sdlc < migration_add_password_resets.sql

USE ai_sdlc;

CREATE TABLE IF NOT EXISTS password_resets (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT NOT NULL,
    token           VARCHAR(64) NOT NULL,
    expires_at      DATETIME NOT NULL,
    used            TINYINT(1) NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_password_resets_token (token),

    CONSTRAINT fk_password_resets_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,

    INDEX idx_password_resets_user (user_id)
) ENGINE=InnoDB;
