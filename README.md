# Psykometrisk spørgeskema-app

Generel webapp til import af psykometriske spørgeskemaer (JSON), udstedelse af adgangskoder til
afdelinger, pseudonym besvarelse og psykometrisk analyse. Første instrument: oplevet egen mestring,
teamets fælles mestring, om den nuværende ramme kan rumme situationen, og om det kan forventes af en almen
ramme – på tværs af ti hverdagsdomæner med konkrete adfærdsudtryk (ikke diagnoser).

> **Bemærk:** Instrumentet i `data/sample_almenramme_survey.json` (30 scenarier × 4 perspektiver = 120
> spørgsmål, 10 domæner) er genereret af `scripts/build_sample_survey.py` efter retningslinjerne i
> Shaughnessy m.fl., *Research Methods in Psychology* (2012), kap. 5. Det er **ikke pilottestet eller
> valideret**. Se `docs/instrument.md` for konstrukt, adfærdsudtryk, begrundelse og de trin
> (ekspertgennemgang, pretest), der mangler før reel brug.

## Arkitektur

```
Browser ──HTTPS──▶ Din reverse proxy (TLS) ──HTTP──▶ 127.0.0.1:8000
                                                    │  edge-netværk
                                                    ▼
                FastAPI / Uvicorn (2 workers, statiske filer, CSP/HSTS m.fl.)  ── qa_api ──┐
                                                          │ backend-netværk (internal: true)
                Analyse-worker (Python)        ── qa_worker┤
                Migrate (Alembic, kortlivet)   ── qa_migrate
                                                          ▼
                                   MariaDB 11.4 (kryptering i hvile, 4 databaser)
```

| Database | Indhold | qa_api | qa_worker |
|---|---|---|---|
| `qa_identity` | admins, sessioner, adgangskode-hashes, rate limits | DML | – |
| `qa_data` | organisation, instrumenter, pseudonyme besvarelser | DML | SELECT |
| `qa_analysis` | analysekørsler/resultater | SELECT/INSERT/DELETE | SELECT/UPDATE |
| `qa_audit` | hash-kædet auditlog | SELECT/INSERT | SELECT/INSERT |

Frontend er vanilla HTML/CSS/JS uden build-trin og uden tredjepartsscripts (CSP `script-src 'self'`,
`require-trusted-types-for 'script'; trusted-types 'none'` – ingen `innerHTML` nogen steder).

Afvigelser fra specifikationens forslag (§13) er bevidste valg efter ønske om FastAPI + MariaDB:
statistik i Python (numpy/scipy/statsmodels) i stedet for R; jobkø i MariaDB (`FOR UPDATE SKIP LOCKED`)
i stedet for Redis; lokale admin-konti med Argon2id + obligatorisk TOTP i stedet for Entra ID (OIDC
er næste skridt). MariaDB har ikke row-level security – se `docs/threat-model.md` for kompensation.

## Lokal start

Krav: Docker med Compose v2, `openssl`.

```bash
./scripts/init-secrets.sh                 # genererer .env + MariaDB-krypteringsnøgler (secrets/)
docker compose up -d --build              # db → migrate → api (2 workers) + worker
docker compose exec api python -m app.cli create-sysadmin <brugernavn>
docker compose exec api python -m app.cli seed-demo     # valgfrit: SYNTETISK demo-tenant
```

Appen lytter på HTTP på `127.0.0.1:8000` (`APP_BIND`/`APP_PORT`). Peg din egen reverse proxy
(TLS) derhen og sæt `PUBLIC_HOST`/`PUBLIC_PORT` til den offentlige adresse – den bruges til
Origin-tjek, og cookies er `__Host-`/`Secure`, så login kræver HTTPS gennem proxyen.

- Respondent: `https://<PUBLIC_HOST>/`
- Admin: `https://<PUBLIC_HOST>/admin/`

Krav til proxyen: videresend `X-Forwarded-For` og `X-Forwarded-Proto` (uvicorn stoler kun på dem fra
`FORWARDED_ALLOW_IPS`), begræns request body til ~2 MB, og maskér/udelad IP og cookies i adgangsloggen.

Systemadmin har bevidst ikke adgang til tenant-indhold. For at oprette spørgeskemaer: opret en tenant
under fanen *Tenants* med en første organisationsadmin, og log ind som den bruger. Mistet
engangsadgangskode: `docker compose exec api python -m app.cli reset-password <brugernavn>`.
Organisationen har to niveauer: **institutioner** (skole, dagtilbud, andet) og under dem
**afdelinger/klasser** (fanen *Institutioner*). Navne er unikke pr. institution. Adgangskoder kan
udstedes til en afdeling/klasse eller hele institutionen. Under *Resultater* sammenlignes institutioner,
når ingen er valgt; vælges en institution, vises dens samlede resultat og en sammenligning af dens
afdelinger/klasser. En afdelingsadmin for en institution har adgang til alle dens afdelinger/klasser.
Eksporter har kolonnen `institution_id`.

Systemadmin kan slette en tenant (fanen *Tenants* → *Slet*, bekræft ved at skrive navnet). Det sletter
permanent afdelinger, spørgeskemaer (også publicerede), adgangskoder, besvarelser, analyser og brugere
der kun har adgang til den tenant. Auditloggen bevares.

Engangsadgangskoder udskrives én gang. Ved første login opsættes TOTP (QR-kode) og adgangskoden skal
skiftes (min. 14 tegn). `seed-demo` opretter `demo.org` (organisationsadmin med eksportret),
`demo.unit` (afdelingsadmin), seks afdelinger (3 dagtilbud, 3 skole), én kode pr. afdeling og ca. 150
syntetiske besvarelser markeret `is_synthetic=1`.

### Migrationer

Kører automatisk via `migrate`-servicen ved `docker compose up`. Manuelt:

```bash
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic downgrade -1
```

Publicerede spørgeskemaversioner er beskyttet af DB-triggere (kan ikke ændres eller slettes).

## Test

```bash
docker compose --profile test run --rm test          # 65 tests: unit, property, statistik, integration, arkitektur
python3 scripts/smoke_test.py --code <KODE> --admin <bruger> --password <pw> --new-password <ny>
```

- `tests/test_randomization.py` – property-tests (Hypothesis): alle items én gang, belonging sidst,
  gap-regel når matematisk mulig, eksakt modbalancering, determinisme.
- `tests/test_scoring.py` – golden tests inkl. reverse scoring, missing og 80 %-tærskel.
- `tests/test_stats.py` – mod scipy/statsmodels og kendte værdier (alfa, omega, Welch, Games-Howell,
  Hedges g, ICC, rwg(j), mixed model, sekundær celleundertrykkelse).
- `tests/test_schema.py` – JSON-schema contract tests.
- `tests/test_integration.py` – migrations-roundtrip, MVP-flow, genoptagelse, tenant-isolation,
  autorisation, CSRF/MFA, rate limiting, celleundertrykkelse, reproducerbar eksport, auditkæde.

Integrationstests kører i separate `test_qa_*`-databaser og rører aldrig produktionsdata.

### Tilgængelighedstest (axe + Playwright)

```bash
cd tests/e2e && docker run --rm --network host -e E2E_CODE=<KODE> -v $PWD:/e2e -v /tmp:/out \
  -w /tmp/w mcr.microsoft.com/playwright:v1.49.1-jammy \
  bash -c "cp /e2e/package.json /e2e/a11y.mjs . && npm install && node a11y.mjs"
```

Kører WCAG 2.0–2.2 AA-regler på desktop og mobil, tjekker tastaturbetjening af radiogrupper,
autosave, genindlæsning og at der ingen CSP/Trusted Types-overtrædelser er. Manuel
skærmlæsertest (NVDA/VoiceOver) skal stadig udføres før produktion.

## Persondata og juridiske sider

Appen serverer `/privatliv/` (privatlivspolitik), `/databehandling/` (roller, foranstaltninger, underdatabehandlere, brud) og `/cookies/`.
Driftsoplysninger hentes fra `OPERATOR_*`-variablerne via `/api/public/legal-info`; tomme felter vises som »ikke angivet«.
Appen bruger kun to strengt nødvendige 1.-parts-cookies (`__Host-qa_resp`, `__Host-qa_admin`) og ingen browserlagring, så der er intet cookiebanner.

Registreredes rettigheder (art. 15, 17, 20) kan udøves af respondenten selv med den **personlige kode**, der vises ved start: `POST /api/respondent/rights/export`
og `/rights/erase` (UI: `/#rettigheder`). Koden bevares efter afslutning og udløber med opbevaringsperioden.

## Syntetisk datasæt

```bash
docker compose exec api python -m app.cli export-synthetic > data/synthetic/synthetic_long.csv
```

Svarværdier er reproducerbare ud fra seed `20241119`; id'er og tidsstempler genereres ved seeding.

## Drift og deployment

1. Sæt `PUBLIC_HOST` til det rigtige domæne (og `PUBLIC_PORT` hvis ikke 443); TLS/certifikat
   håndteres af din reverse proxy. Hosting skal ligge i EU/EØS.
2. Hæv `HSTS_MAX_AGE` gradvist (300 → 31536000).
3. Erstat `.env`/`secrets/` med managed secrets (Docker/K8s secrets, Vault). Tag sikker backup af
   `secrets/mariadb-*` – uden dem kan databasen og backups ikke læses.
4. Backup: `BACKUP_GPG_RECIPIENT=<nøgle> ./scripts/backup.sh` – dump pipes direkte til GPG (AES-256, offentlig nøgle), så der aldrig ligger klartekst på disken
   og serveren ikke kan dekryptere sine egne backups. Rotation via `BACKUP_KEEP_DAYS` (standard 35). Test gendannelse jævnligt.
5. Opbevaring: pr. tenant (`retentionMonths`, standard 24). Sletning kører hver time og kan startes
   af systemadmin (`POST /api/admin/system/retention`).
6. Udfyld `OPERATOR_*`, `DPO_CONTACT`, `SECURITY_CONTACT`, `HOSTING_*` i `.env` (vises på de juridiske sider). DPIA, databehandleraftale og oplysningstekst
   (survey-JSON `respondentInfo` + tenant `dataController`/`contact`) skal være på plads før produktion. Se `docs/compliance/` for tjekliste og skabeloner.

## Dokumentation

- `docs/data-model.md` – datamodeldiagram
- `docs/threat-model.md` – trusselsmodel og sikkerhedskontroller
- `docs/compliance/` – GDPR-tjekliste, sikkerhedskontroller (Datatilsynet/ISO 27001/ENISA), DPIA, ROPA, DPA-skabelon, brudhåndtering, køreplan til ISO 27001/27701
- `SECURITY.md` – ansvarlig offentliggørelse af sårbarheder
- `docs/frontend-design.md` – designsystem og tilpasninger (CSP, WCAG, selvhostede skrifttyper/ikoner)
- `docs/instrument.md` – instrumentets konstrukt, domæner, designvalg og validitetsplan
- `docs/analysis-protocol.md` – analyseprotokol (scoring, missing, modeller, undertrykkelse)
- `schema/survey.schema.json` – importformat
