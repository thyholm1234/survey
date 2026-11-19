#!/usr/bin/env bash
# Krypteret backup af alle fire databaser (GDPR art. 32: tilgængelighed + fortrolighed af backups).
#
# Backups er ALDRIG klartekst: dumpet pipes direkte til GPG (AES-256, public key-kryptering), så
# der aldrig ligger en ukrypteret fil på disken, og så serveren ikke kan dekryptere sine egne backups
# (den private nøgle opbevares offline/adskilt – fx i en nøgleboks hos databeskyttelsesansvarlig).
#
# Krav : docker compose-stakken kører; offentlig GPG-nøgle importeret (gpg --import offentlig.asc).
# Brug : BACKUP_GPG_RECIPIENT=backup@example.dk ./scripts/backup.sh
# Valgfrit: BACKUP_DIR (./backups), BACKUP_KEEP_DAYS (35; opbevaringsbegrænsning gælder også backups!)
# Gendan: gpg --decrypt qa-<tid>.sql.gz.gpg | gunzip | docker compose exec -T db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD"'
# Test gendannelse mindst kvartalsvis og dokumentér resultatet (ISO 27001 A.8.13).
set -euo pipefail
cd "$(dirname "$0")/.."

: "${BACKUP_GPG_RECIPIENT:?Sæt BACKUP_GPG_RECIPIENT til nøgle-id/e-mail på den OFFENTLIGE backupnøgle}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${BACKUP_KEEP_DAYS:-35}"

umask 077
mkdir -p "$BACKUP_DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
out="$BACKUP_DIR/qa-$ts.sql.gz.gpg"
tmp="$out.partial"
trap 'rm -f "$tmp"' EXIT

docker compose exec -T db sh -c \
  'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers --events \
     --databases qa_identity qa_data qa_analysis qa_audit' \
  | gzip -9 \
  | gpg --batch --yes --trust-model always --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
        --cipher-algo AES256 --compress-algo none -o "$tmp"

# pipefail afbryder, hvis mariadb-dump eller gpg fejler; en tom fil må aldrig stå som 'gyldig' backup
[ -s "$tmp" ] || { echo "Backup er tom – afbrudt." >&2; exit 1; }
mv "$tmp" "$out"
sha256sum "$out" > "$out.sha256"
find "$BACKUP_DIR" -maxdepth 1 -name 'qa-*.gpg*' -mtime +"$KEEP" -delete
echo "OK: $out (krypteret, ældre end $KEEP dage slettet)"
