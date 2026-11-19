# Trusselsmodel (kort, STRIDE-baseret)

## Aktiver
1. Pseudonyme besvarelser (personoplysninger – pseudonymisering er ikke anonymisering).
2. Adgangskoder til respondentgrupper og genoptagelseskoder.
3. Admin-konti, sessioner og eksportrettigheder.
4. Instrumentets integritet (publicerede versioner) og analysernes reproducerbarhed.
5. Auditlog.

## Aktører
Anonym internetbruger · respondent · afdelingsadmin · organisationsadmin · systemadmin ·
kompromitteret API-proces · kompromitteret worker · ondsindet administrator i anden tenant.

## Trusler og kontroller

| # | Trussel | Kontrol |
|---|---|---|
| S1 | Brute force af respondentkoder | 12 tegn fra 31-tegns alfabet (~59 bit); Argon2id-hash + peppered HMAC-opslag; 5 mislykkede forsøg/15 min pr. pseudonymiseret IP; generisk fejlbesked; dummy-hash ved ukendt kode (ens svartid). |
| S2 | Credential stuffing mod admins | Argon2id; obligatorisk TOTP med replay-beskyttelse; rate limit pr. IP og pr. brugernavn; kontolås efter 10 fejl; min. 14 tegns adgangskode. |
| S3 | Session hijacking / fixation | `__Host-`-cookies, `Secure; HttpOnly; SameSite=Strict`; token gemmes kun som SHA-256; rotation efter MFA; glidende + absolut udløb; logout sender `Clear-Site-Data`. |
| T1 | CSRF | SameSite=Strict, CSRF-token-header for admins, Origin-tjek, påkrævet `application/json`, Fetch Metadata afviser cross-site før autentifikation. |
| T2 | XSS / DOM-XSS | Ingen `innerHTML`; CSP `script-src 'self'`, `object-src 'none'`, `base-uri 'none'`; `require-trusted-types-for 'script'; trusted-types 'none'`; ingen tredjepartsscripts. |
| T3 | Manipulation af publiceret instrument | Publicering er envejs; DB-triggere blokerer UPDATE/DELETE/INSERT på publicerede versioner og deres items; SHA-256 af kilde gemmes og auditeres. |
| T4 | Manipulation af auditlog | Hash-kæde (SHA-256) serialiseret med `GET_LOCK`; `qa_api`/`qa_worker` har kun INSERT/SELECT; verifikation via API/CLI. |
| T5 | CSV/formel-injektion i eksport | Celler der starter med `= + - @ \t \r` præfikses med `'`. |
| R1 | Benægtelse af adminhandlinger | Audit af login, MFA, import, publicering, kodeoprettelse, deaktivering, dashboardvisning, analyse, eksport, sletning. |
| I1 | Tenant-overgreb (IDOR) | Alle admin-endpoints går gennem `Principal`; ikke-gætbare 128-bit id'er; 404 i stedet for 403; dedikerede isolationstests. **MariaDB har ingen RLS** – kompensation: ét autorisationslag + tests + DB-privilegieadskillelse. |
| I2 | Re-identifikation via små grupper | Minimumscellestørrelse (≥10, pr. tenant); sekundær undertrykkelse i afdelingssammenligning; komplementregel for filtre; rækkeeksport kræver eksportret og n ≥ k. |
| I3 | Identifikation via metadata | Ingen navn/e-mail/CPR/fritekst; ingen IP i analysedata; IP kun som dagligt roterende HMAC i rate-limit-tabellen (slettes ved udløb); ekstern reverse proxy skal maskere IP og fjerne cookies i sin log; uvicorn access-log slået fra; kun browser- og skærmklasse gemmes. |
| I4 | Systemadmin læser besvarelser | Systemadmin har ingen tenant-scope som standard og får 404 på dashboard/eksport. |
| I5 | Kompromitteret worker | Kan kun læse `qa_data` og skrive analyseresultater; ingen adgang til identitetsdata. |
| I6 | Kompromitteret API | Ingen DDL; kan ikke ændre auditlog eller publicerede instrumenter; adgangskoder findes ikke i klartekst. |
| I7 | Data-at-rest / backup-tyveri | MariaDB `file_key_management` med krypteret nøglefil, `innodb_encrypt_tables=FORCE`, krypteret redo-log, temp og binlog. Nøgler skal i produktion ligge i managed secrets/KMS. |
| I8 | Netværksaflytning | TLS i ekstern reverse proxy; HSTS sat af appen; api publiceret kun på 127.0.0.1 som standard; DB på `internal: true`-netværk uden publiceret port. |
| D1 | Overbelastning | Request-størrelse 2 MB (app; bør også håndhæves i reverse proxy); uvicorn `--limit-concurrency`; Argon2id-omkostning begrænset af rate limits; analyser kører asynkront i worker. |
| E1 | Privilegieeskalering via brugeroprettelse | Kun systemadmin kan oprette systemadmins; org-admin kun i egen tenant; afdelingsadmin kan ikke oprette brugere. |
| E2 | Container-udbrud | Ikke-root brugere, `read_only`, `cap_drop: ALL`, `no-new-privileges`, hash-pinnede Python-afhængigheder (`--require-hashes`). |

## Kendte restrisici / åbne punkter før produktion
- Ingen OIDC/Entra ID endnu; lokale konti med TOTP.
- Ingen TLS mellem API og MariaDB (samme host, internt netværk). Aktivér ved separat DB-host.
- Differencing over tid (gentagne dashboardvisninger med forskellige datofiltre efterhånden som nye
  svar kommer ind) er kun delvist afbødet af komplementreglen.
- Tidsstempler og svartider i rækkeeksport er kvasi-identifikatorer; eksport bør begrænses til
  analytikere med dokumenteret formål.
- Manuel skærmlæsertest, penetrationstest og DPIA mangler.
