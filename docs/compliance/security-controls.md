# Sikkerhedskontroller og afstemning med standarder

Hver række: kontrol → hvor den findes (bevis) → status. Afstemningen mod Datatilsynets katalog og ISO/IEC 27001:2022 Annex A er **egenvurdering**, ikke en revision.
Hent altid den gældende udgave af Datatilsynets *Katalog over foranstaltninger* og vurdér pr. foranstaltning, hvilke der er relevante for din risiko (kataloget er et værktøj, ikke en tjekliste, der skal opfyldes i sin helhed).

## A. Kontroloversigt (Datatilsynet art. 32-temaer ↔ ISO 27001:2022 Annex A)

| Tema | Kontrol i løsningen | Bevis | ISO A. | Status |
|---|---|---|---|---|
| **Adgangsstyring** | Rollemodel (system/org/afdeling), mindste privilegium, tenant-isolation (404 frem for 403), eksportret adskilt | `deps.py`, `test_integration` (isolation, autorisation) | 5.15, 5.18, 8.2, 8.3 | ✅ |
| **Autentifikation** | Argon2id, ≥ 14 tegn, obligatorisk TOTP med replay-beskyttelse, rate limit + kontolås, sessionsrotation efter MFA, glidende + absolut udløb, `Clear-Site-Data` ved logout | `routers/admin_auth.py`, `security.py` | 5.17, 8.5 | ✅ (SSO/OIDC ⬜) |
| **Kryptering i transit** | TLS 1.2+ i reverse proxy; HSTS; `Secure`/`__Host-` cookies; `upgrade-insecure-requests`; API kun på 127.0.0.1 | `main.py`, `docker-compose.yml` | 8.24 | 🟡 proxy-konfiguration skal verificeres i drift |
| **Kryptering i hvile** | MariaDB `innodb_encrypt_tables=FORCE`, krypteret redo/temp/binlog; TOTP-hemmeligheder krypteret (Fernet); koder/nøgler kun som hash; **backups GPG-krypteret** | `db/conf/99-hardening.cnf`, `scripts/backup.sh` (testet) | 8.24, 8.13 | ✅ (nøglestyring/KMS 🟡) |
| **Pseudonymisering** | Ingen direkte identifikatorer; registrerede-holdt personlig kode; IP kun som roterende HMAC; k-anonymitet i output | `models.py`, `services/dashboard.py`, ENISA 2019 | 8.11 | ✅ |
| **Adskillelse** | 4 databaser (identity/data/analysis/audit), 4 DB-brugere med minimale rettigheder; worker uden adgang til identitetsdata; internt netværk uden publiceret DB-port | `db/init`, `docker-compose.yml` | 8.31, 8.22 | ✅ |
| **Logning og overvågning** | Hash-kædet auditlog (INSERT/SELECT kun); kæde-verifikation; ingen IP/cookies i app-log | `audit.py`, `GET /api/admin/audit/verify` | 8.15, 8.16 | ✅ log / ⬜ central overvågning, alarmer, SIEM |
| **Sletning/opbevaring** | Automatisk retention; rettighedsendpoint; tenant-sletning; backup-rotation | `services/retention.py`, `scripts/backup.sh` | 8.10, 5.34 | ✅ (auditlog 🟡) |
| **Backup og gendannelse** | Krypteret, rotation, checksum; **gendannelsestest ikke planlagt/udført** | `scripts/backup.sh` | 8.13, 5.30 | 🟡 |
| **Sikker udvikling** | CSP + Trusted Types, ingen `innerHTML`, CSRF + Fetch Metadata + Origin-tjek, inputvalidering (Pydantic `extra=forbid`), parametriserede SQL-værdier, hash-pinnede afhængigheder, test (64) i CI | `main.py`, `backend/tests`, `.github/workflows/ci.yml` | 8.25–8.29, 8.28 | ✅ |
| **Sårbarhedshåndtering** | Ugentlig pip-audit/Bandit/gitleaks/Trivy + Dependabot (`.github/workflows/security.yml`). **Fund ved gennemgang 2026-11-19:** starlette 0.41.3 (14) og cryptography 44.0.0 (12) havde kendte sårbarheder → opgraderet til starlette 1.10.0 / cryptography 50.0.2; pytest 8.3.4 → 9.0.3; pip-audit: 0 kendte | `backend/requirements*.txt`, CI | 8.8 | ✅ |
| **Ekstern test** | Ingen penetrationstest udført | – | 8.29, 5.35 | ⬜ |
| **Driftsmiljø (container)** | Ikke-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`, tmpfs, healthchecks, Trivy | `docker-compose.yml`, `Dockerfile` | 8.9, 8.19 | ✅ |
| **Netværk** | Segmenterede docker-netværk, DB `internal: true`, rate limits, `--limit-concurrency` | `docker-compose.yml` | 8.20, 8.22, 8.6 | ✅ (WAF/DDoS i proxy/udbyder 🟡) |
| **Tilgængelighed (CIA)** | Healthcheck, restart-politik, backup; ingen redundans/HA, ingen RTO/RPO fastlagt | – | 5.29, 5.30, 8.14 | 🟡 |
| **Leverandørstyring** | Underdatabehandlere oplistet; aftaler skal indgås | `/databehandling/`, [`dpa-template.md`](dpa-template.md) | 5.19–5.23 | 🟡 |
| **Hændelseshåndtering** | Procedure udarbejdet; ikke indøvet | [`incident-response.md`](incident-response.md) | 5.24–5.28 | 🟡 |
| **Organisatorisk (politikker, roller, uddannelse, adgangsreview, ledelsens gennemgang, intern audit)** | Ikke dækket af kode | [`iso27001-roadmap.md`](iso27001-roadmap.md) | 5.1–5.4, 6.3, 5.36, 9.x | ⬜ |
| **Fysisk sikkerhed** | Arves fra hostingudbyder (skal dokumenteres, fx ISO 27001-certifikat) | DPA/underdatabehandler | 7.x | 🟡 |

## B. Webapplikationssikkerhed (OWASP ASVS-orienteret egenvurdering)

| ASVS-kapitel | Dækning | Bemærkning |
|---|---|---|
| V2 Autentifikation | ✅ | Argon2id, MFA, rate limit, ingen standardhemmeligheder (afvises ved opstart) |
| V3 Session | ✅ | `__Host-`, HttpOnly, SameSite=Strict, hashet token, rotation, udløb |
| V4 Adgangskontrol | ✅ | Centralt `Principal`, tenant-isolationstests |
| V5 Validering/kodning | ✅ | Pydantic strict, ingen `innerHTML`, CSV-formelinjektionsværn |
| V7 Fejl/logning | ✅ | Generiske fejl, ingen inputværdier tilbage, ingen persondata i log |
| V8 Databeskyttelse | ✅ | Pseudonymisering, kryptering, `Cache-Control: no-store` |
| V9 Kommunikation | 🟡 | TLS i proxy |
| V10 Ondsindet kode / V14 Konfiguration | ✅ | Hash-pinnede afhængigheder, sikkerhedshoveder (CSP, COOP/CORP/COEP, Permissions-Policy) |
| V12/V13 Filer/API | ✅ | Kun JSON, 2 MB-grænse, ingen filupload ud over schema-valideret import |

**Bandit (2026-11-19):** 0 høj. 19 medium (alle B608, SQL via f-string) er gennemgået: tabelnavne stammer fra konstanter via `qualified()`, alle værdier er bundne parametre → falske positiver, udeladt i CI (`--skip B608`) med forklaring.
3 lav: B311 ×2 (`random` til spørgsmålsrækkefølge, hvis seed genereres med `secrets.randbits`, og til syntetiske data – ikke en sikkerhedsfunktion) og B101 (`assert` i CLI-seed-kommandoen).

## C. Kendte åbne punkter (prioriteret)
1. Ekstern penetrationstest og remediering (⬜).
2. Central logindsamling og alarmer (login-fejl, tenant-sletning, eksport, kæde-brud) (⬜).
3. Auditlog-opbevaring med arkivering (🟡, se retention).
4. Nøglestyring i KMS/Vault + roteringsprocedure (🟡).
5. Gendannelsestest og RTO/RPO (🟡).
6. SSO/OIDC for administratorer med MFA hos IdP (⬜).
7. Manuel skærmlæsertest og tilgængelighedserklæring (🟡).
8. Ledelsessystem (ISMS) – se [`iso27001-roadmap.md`](iso27001-roadmap.md) (⬜).
