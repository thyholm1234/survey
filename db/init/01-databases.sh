#!/bin/bash
# Opretter adskilte databaser og mindste-privilegie-brugere.
#  qa_identity : admins, sessioner, adgangskoder, rate-limit (identitets-/adgangsdata)
#  qa_data     : organisation, spørgeskemaer, besvarelser (pseudonyme analysedata)
#  qa_analysis : analysekørsler og resultater
#  qa_audit    : append-only auditlog (api/worker må kun INSERT/SELECT)
set -euo pipefail
mariadb -uroot -p"${MARIADB_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS qa_identity CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS qa_data     CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS qa_analysis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS qa_audit    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Migrationsbruger: DDL, kører kun i den kortlivede migrate-container
CREATE USER IF NOT EXISTS 'qa_migrate'@'%' IDENTIFIED BY '${DB_MIGRATE_PASSWORD}';
GRANT ALL PRIVILEGES ON qa_identity.* TO 'qa_migrate'@'%';
GRANT ALL PRIVILEGES ON qa_data.*     TO 'qa_migrate'@'%';
GRANT ALL PRIVILEGES ON qa_analysis.* TO 'qa_migrate'@'%';
GRANT ALL PRIVILEGES ON qa_audit.*    TO 'qa_migrate'@'%';
-- Testdatabaser (bruges kun af test-profilen)
GRANT ALL PRIVILEGES ON \`test\_qa\_%\`.* TO 'qa_migrate'@'%';

-- API: DML, ingen DDL. Auditlog kun INSERT/SELECT.
CREATE USER IF NOT EXISTS 'qa_api'@'%' IDENTIFIED BY '${DB_API_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON qa_identity.* TO 'qa_api'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON qa_data.*     TO 'qa_api'@'%';
GRANT SELECT, INSERT, DELETE         ON qa_analysis.* TO 'qa_api'@'%';
GRANT SELECT, INSERT                 ON qa_audit.*    TO 'qa_api'@'%';

-- Worker: læser analysedata, skriver kun analyseresultater. Ingen adgang til identitetsdata.
CREATE USER IF NOT EXISTS 'qa_worker'@'%' IDENTIFIED BY '${DB_WORKER_PASSWORD}';
GRANT SELECT                 ON qa_data.*     TO 'qa_worker'@'%';
GRANT SELECT, UPDATE         ON qa_analysis.* TO 'qa_worker'@'%';
GRANT SELECT, INSERT         ON qa_audit.*    TO 'qa_worker'@'%';

-- Fjern anonyme/test-standarder
DELETE FROM mysql.global_priv WHERE User='';
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
SQL
