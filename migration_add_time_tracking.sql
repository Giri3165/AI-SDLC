-- Run this against your EXISTING ai_sdlc database to add
-- time tracking and budget/cost tracking.
--
--   mysql -u root -p ai_sdlc < migration_add_time_tracking.sql

USE ai_sdlc;

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS hourly_rate DECIMAL(8,2) NULL,
    ADD COLUMN IF NOT EXISTS budget_amount DECIMAL(10,2) NULL;

CREATE TABLE IF NOT EXISTS time_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    task_id         INT NOT NULL,
    user_id         INT NOT NULL,
    hours           DECIMAL(5,2) NOT NULL,
    log_date        DATE NOT NULL,
    notes           VARCHAR(255) NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_time_logs_hours CHECK (hours > 0 AND hours <= 24),

    CONSTRAINT fk_time_logs_task
        FOREIGN KEY (task_id) REFERENCES tasks(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_time_logs_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,

    INDEX idx_time_logs_task (task_id),
    INDEX idx_time_logs_user (user_id)
) ENGINE=InnoDB;
