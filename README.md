# Psykometrisk spørgeskema-app

Generel webapp til import af psykometriske spørgeskemaer (JSON), udstedelse af adgangskoder til
afdelinger, pseudonym besvarelse og psykometrisk analyse. Første instrument: oplevet egen mestring,
teamets mestring, rammens kapacitet og almen tilhørighed på tværs af ti funktionsdomæner.

> **Bemærk:** Specifikationens bilag `sample_almenramme_survey.json` var ikke vedlagt. Filen i
> `data/` er en strukturelt tro **DEMO-rekonstruktion** (40 adfærdsbeskrivelser × 4 perspektiver = 160
> spørgsmål, 10 domæner) genereret af `scripts/build_sample_survey.py`. Ordlyden er ikke valideret.
> Erstat den med det rigtige instrument via admin-importen.

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
docker compose --profile test run --rm test          # 59 tests: unit, property, statistik, integration
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
4. Backup: `mariadb-dump` fra `db`-containeren; backups er klartekst-SQL og skal krypteres separat.
5. Opbevaring: pr. tenant (`retentionMonths`, standard 24). Sletning kører hver time og kan startes
   af systemadmin (`POST /api/admin/system/retention`).
6. DPIA, databehandleraftale og oplysningstekst (survey-JSON `respondentInfo` + tenant
   `dataController`/`contact`) skal være på plads før produktion.

## Dokumentation

- `docs/data-model.md` – datamodeldiagram
- `docs/threat-model.md` – trusselsmodel og sikkerhedskontroller
- `docs/analysis-protocol.md` – analyseprotokol (scoring, missing, modeller, undertrykkelse)
- `schema/survey.schema.json` – importformat
