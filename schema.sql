-- ============================================================
-- AI-SDLC System — Full Database Schema
-- Run this once against a fresh MySQL database:
--   mysql -u root -p < schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS ai_sdlc
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ai_sdlc;

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    fullname        VARCHAR(150)    NOT NULL,
    email           VARCHAR(150)    NOT NULL,
    username        VARCHAR(50)     NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    role            ENUM('Client','Project Manager','Developer','Tester','Admin') NOT NULL,
    failed_login_attempts  TINYINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until    DATETIME NULL,
    must_change_password   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email),
    INDEX idx_users_role (role)
) ENGINE=InnoDB;

-- ============================================================
-- PROJECTS
-- ============================================================

CREATE TABLE projects (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    project_name    VARCHAR(200)    NOT NULL,
    description     TEXT,
    category        VARCHAR(100),
    priority        ENUM('Low','Medium','High') NOT NULL DEFAULT 'Medium',
    status          ENUM('Pending','Approved','Planning','Development',
                          'Testing','Deployment','Completed','Rejected')
                    NOT NULL DEFAULT 'Pending',
    progress        TINYINT UNSIGNED NOT NULL DEFAULT 0,

    client_id       INT NOT NULL,
    manager_id      INT NULL,

    start_date      DATE NULL,
    end_date        DATE NULL,

    hourly_rate     DECIMAL(8,2)  NULL,
    budget_amount   DECIMAL(10,2) NULL,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_projects_progress CHECK (progress BETWEEN 0 AND 100),

    CONSTRAINT fk_projects_client
        FOREIGN KEY (client_id) REFERENCES users(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_projects_manager
        FOREIGN KEY (manager_id) REFERENCES users(id)
        ON DELETE SET NULL,

    INDEX idx_projects_client (client_id),
    INDEX idx_projects_manager (manager_id),
    INDEX idx_projects_status (status)
) ENGINE=InnoDB;

-- ============================================================
-- REQUIREMENTS
-- ============================================================

CREATE TABLE requirements (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    project_id      INT NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    priority        ENUM('Low','Medium','High') NOT NULL DEFAULT 'Medium',
    status          ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
    created_by      INT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_requirements_project
        FOREIGN KEY (project_id) REFERENCES projects(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_requirements_creator
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON DELETE RESTRICT,

    INDEX idx_requirements_project (project_id)
) ENGINE=InnoDB;

-- ============================================================
-- TASKS
-- ============================================================

CREATE TABLE tasks (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    requirement_id  INT NOT NULL,
    project_id      INT NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    assigned_to     INT NULL,
    priority        ENUM('Low','Medium','High') NOT NULL DEFAULT 'Medium',
    status          ENUM('Pending','Assigned','In Progress','Testing','Completed')
                    NOT NULL DEFAULT 'Pending',
    progress        TINYINT UNSIGNED NOT NULL DEFAULT 0,
    due_date        DATE NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_tasks_progress CHECK (progress BETWEEN 0 AND 100),

    CONSTRAINT fk_tasks_requirement
        FOREIGN KEY (requirement_id) REFERENCES requirements(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_tasks_project
        FOREIGN KEY (project_id) REFERENCES projects(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_tasks_assignee
        FOREIGN KEY (assigned_to) REFERENCES users(id)
        ON DELETE SET NULL,

    INDEX idx_tasks_requirement (requirement_id),
    INDEX idx_tasks_project (project_id),
    INDEX idx_tasks_assigned (assigned_to)
) ENGINE=InnoDB;

-- ============================================================
-- TIME LOGS
-- ============================================================

CREATE TABLE time_logs (
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

-- ============================================================
-- BUGS
-- ============================================================

CREATE TABLE bugs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    project_id      INT NOT NULL,
    task_id         INT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    severity        ENUM('Low','Medium','High','Critical') NOT NULL DEFAULT 'Medium',
    status          ENUM('Open','In Progress','Resolved','Closed','Reopened')
                    NOT NULL DEFAULT 'Open',
    reported_by     INT NOT NULL,
    assigned_to     INT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP NULL,

    CONSTRAINT fk_bugs_project
        FOREIGN KEY (project_id) REFERENCES projects(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_bugs_task
        FOREIGN KEY (task_id) REFERENCES tasks(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_bugs_reporter
        FOREIGN KEY (reported_by) REFERENCES users(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_bugs_assignee
        FOREIGN KEY (assigned_to) REFERENCES users(id)
        ON DELETE SET NULL,

    INDEX idx_bugs_project (project_id),
    INDEX idx_bugs_task (task_id),
    INDEX idx_bugs_assigned (assigned_to)
) ENGINE=InnoDB;

-- ============================================================
-- DEPLOYMENTS
-- ============================================================

CREATE TABLE deployments (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    project_id          INT NOT NULL,
    version             VARCHAR(50) NOT NULL,
    environment         VARCHAR(50) NOT NULL DEFAULT 'Production',
    deployment_date     DATE NOT NULL,
    status              ENUM('Pending','Deployed','Failed','Rolled Back')
                        NOT NULL DEFAULT 'Pending',
    notes               TEXT,
    deployed_by         INT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_deployments_project
        FOREIGN KEY (project_id) REFERENCES projects(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_deployments_deployer
        FOREIGN KEY (deployed_by) REFERENCES users(id)
        ON DELETE SET NULL,

    INDEX idx_deployments_project (project_id)
) ENGINE=InnoDB;

-- ============================================================
-- PASSWORD RESETS
-- ============================================================

CREATE TABLE password_resets (
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

-- ============================================================
-- DELETED PROJECTS (audit history — full JSON snapshot)
-- ============================================================

CREATE TABLE deleted_projects (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    project_id          INT NOT NULL,
    project_snapshot    JSON NOT NULL,
    deleted_by          INT NOT NULL,
    deleted_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason              VARCHAR(255) NULL,

    CONSTRAINT fk_deleted_projects_user
        FOREIGN KEY (deleted_by) REFERENCES users(id)
        ON DELETE RESTRICT,

    INDEX idx_deleted_projects_project (project_id)
) ENGINE=InnoDB;
