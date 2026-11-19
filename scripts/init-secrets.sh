#!/usr/bin/env bash
# Genererer .env og MariaDB-krypteringsnøgler (data-at-rest).
# Overskriver aldrig eksisterende hemmeligheder uden --force.
set -euo pipefail
cd "$(dirname "$0")/.."

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

if [[ -f .env && $FORCE -eq 0 ]]; then
  echo ".env findes allerede – brug --force for at regenerere (ødelægger adgang til eksisterende data!)" >&2
  exit 1
fi

rand_b64() { openssl rand -base64 "$1" | tr -d '\n'; }
rand_pw()  { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 40; }
fernet()   { openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'; }

umask 077
sed \
  -e "s|^MARIADB_ROOT_PASSWORD=.*|MARIADB_ROOT_PASSWORD=$(rand_pw)|" \
  -e "s|^DB_MIGRATE_PASSWORD=.*|DB_MIGRATE_PASSWORD=$(rand_pw)|" \
  -e "s|^DB_API_PASSWORD=.*|DB_API_PASSWORD=$(rand_pw)|" \
  -e "s|^DB_WORKER_PASSWORD=.*|DB_WORKER_PASSWORD=$(rand_pw)|" \
  -e "s|^CODE_LOOKUP_PEPPER=.*|CODE_LOOKUP_PEPPER=$(rand_b64 32)|" \
  -e "s|^IP_HASH_KEY=.*|IP_HASH_KEY=$(rand_b64 32)|" \
  -e "s|^TOTP_ENC_KEY=.*|TOTP_ENC_KEY=$(fernet)|" \
  .env.example > .env
chmod 600 .env

# MariaDB file_key_management: nøglefil krypteret med en separat filekey.
mkdir -p secrets
{
  echo "1;$(openssl rand -hex 32)"
  echo "2;$(openssl rand -hex 32)"
} > secrets/mariadb-keys.txt
openssl rand -hex 128 > secrets/mariadb-filekey
openssl enc -aes-256-cbc -md sha1 -pass file:secrets/mariadb-filekey \
  -in secrets/mariadb-keys.txt -out secrets/mariadb-keys.enc 2>/dev/null
shred -u secrets/mariadb-keys.txt 2>/dev/null || rm -f secrets/mariadb-keys.txt

# MariaDB-containeren kører som uid 999; giv kun den læseadgang.
if [[ $(id -u) -eq 0 ]]; then
  chown 999:999 secrets/mariadb-keys.enc secrets/mariadb-filekey
  chmod 400 secrets/mariadb-keys.enc secrets/mariadb-filekey
else
  chmod 444 secrets/mariadb-keys.enc secrets/mariadb-filekey
  echo "ADVARSEL: ikke root – nøglefiler er læsbare for alle lokale brugere. Brug managed secrets i produktion." >&2
fi
echo "OK: .env og secrets/ genereret. Opbevar backup af secrets/ sikkert – uden dem kan databasen ikke læses."
