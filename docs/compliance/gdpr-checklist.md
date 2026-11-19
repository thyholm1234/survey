# GDPR-tjekliste (artikel for artikel)

Roller: **dataansvarlig** = kunden (kommune/skole/institution), **databehandler** = driftsansvarlig, jf. `/databehandling/`.

| Art. | Krav | Implementering / bevis | Status |
|---|---|---|---|
| 5(1)(a) | Lovlighed, rimelighed, gennemsigtighed | Information før start (`respondentInfo`), `/privatliv/`, `/databehandling/`, `/cookies/`; samtykkefelt kræves af API (`StartIn.consent: Literal[True]`) | ✅ |
| 5(1)(b) | Formålsbegrænsning | Formål i instrument og privatlivspolitik; ingen sekundær brug; ingen reklamer/sporing | ✅ |
| 5(1)(c) | Dataminimering | Ingen navn/e-mail/CPR/fritekst/IP ved svar; kun grov browser/skærmklasse; frivillige baggrundsvariable (`docs/threat-model.md` I3) | ✅ |
| 5(1)(d) | Rigtighed | Respondenten kan rette svar før afslutning (tilbage-navigation, `seq`-versionering) | ✅ |
| 5(1)(e) | Opbevaringsbegrænsning | Automatisk sletning pr. tenant (`services/retention.py`, kører hver time); backups: `BACKUP_KEEP_DAYS`; **auditlog uden sletteregel** | 🟡 ([`retention-and-deletion.md`](retention-and-deletion.md)) |
| 5(1)(f) | Integritet og fortrolighed | Se art. 32 | ✅/🟡 |
| 5(2) | Ansvarlighed (kunne påvise) | Hash-kædet auditlog; publicerede instrumenter uforanderlige (SHA-256 + DB-triggere); denne pakke; CI-sikkerhedstests | ✅ |
| 6 | Retsgrundlag | Fastsættes af dataansvarlig og oplyses ved start. **Bemærk:** samtykke fra ansatte er vanskeligt (ubalance); offentlige arbejdsgivere bruger typisk art. 6(1)(e). Se [`dpia.md`](dpia.md) | 🟡 kunden afgør |
| 7 | Samtykke: kunne påvises, kunne trækkes tilbage | Svar kan kun oprettes med `consent=true`; den information, samtykket gives på, ligger i den uforanderlige, hashede instrumentversion (`response.survey_version_id`); tilbagekaldelse = `POST /api/respondent/rights/erase` (testet) | ✅ |
| 9 | Særlige kategorier | Ikke indsamlet. Spørgsmålene handler om arbejdsoplevelser, ikke helbred eller enkeltbørn; ingen diagnoseord (`scripts/build_sample_survey.py` lint). **Hvis et andet instrument indeholder helbredsdata, kræves art. 9-grundlag og skærpet DPIA** | ✅ for dette instrument |
| 11 | Behandling der ikke kræver identifikation | Rettigheder udøves med personlig kode (ENISA: registrerede-holdt nøgle); uden kode kan besvarelsen ikke findes, og det oplyses | ✅ |
| 12–14 | Information til registrerede | `/privatliv/`, informationsskærm før start (formål, frivillighed, dataansvarlig, opbevaring, kontakt), klageadgang til Datatilsynet | ✅ (kræver udfyldte `OPERATOR_*`) |
| 15 | Indsigt | `POST /api/respondent/rights/export` (testet, `test_data_subject_rights_export_and_erase`) | ✅ |
| 16 | Berigtigelse | Før afslutning; efter afslutning: slet og besvar igen med ny kode | ✅ |
| 17 | Sletning | `POST /api/respondent/rights/erase` (cascade på svar, hændelser, sessioner, nøgle; audit uden personoplysninger); tenant-sletning for hele organisationen | ✅ |
| 18, 21 | Begrænsning, indsigelse | Håndteres via dataansvarlig; teknisk kan en besvarelse slettes (art. 17) – begrænsning uden sletning er ikke bygget | 🟡 |
| 20 | Dataportabilitet | JSON-eksport (art. 15-endpointet) | ✅ |
| 22 | Automatiske afgørelser | Ingen. Ingen profilering af individer; kun gruppe-aggregater | ✅ |
| 24, 25 | Ansvar; databeskyttelse gennem design/standard | Privacy by design: pseudonymitet, k-anonymitet (min. celle ≥ 10), standard = mindst muligt; se `security-controls.md` | ✅ |
| 28 | Databehandler | [`dpa-template.md`](dpa-template.md) (bilag A–D); underdatabehandlere oplistet på `/databehandling/` | 🟡 skal underskrives |
| 30 | Fortegnelse | [`ropa.md`](ropa.md) (begge roller) | 🟡 skal fuldføres af organisationen |
| 32 | Behandlingssikkerhed | [`security-controls.md`](security-controls.md): kryptering, pseudonymisering, adgangsstyring, 2FA, logning, test, backup | ✅/🟡 |
| 33–34 | Brud | [`incident-response.md`](incident-response.md); auditlog muliggør afgrænsning | 🟡 skal indøves |
| 35–36 | DPIA | [`dpia.md`](dpia.md): tærskelvurdering + udfyldt risikodel; skal godkendes af dataansvarlig | 🟡 |
| 37–39 | DPO | Kontaktfelt (`DPO_CONTACT`); udpegelse afgør dataansvarlig | 🟡 |
| 44–49 | Tredjelandsoverførsler | Ingen; hosting i EU/EØS; ingen tredjepartsressourcer (skrifttyper/ikoner selvhostet, CSP `'self'`) | ✅ |
| ePrivacy / cookiebekendtgørelsen | Cookies | Kun to strengt nødvendige 1.-parts-cookies; ingen localStorage; ingen samtykkebanner nødvendigt; `/cookies/` | ✅ |
| Lov om webtilgængelighed (offentlige) | Tilgængelighedserklæring | WCAG 2.2 AA udviklet og axe-testet; **manuel skærmlæsertest og erklæring mangler** | 🟡 |
