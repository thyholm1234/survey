# Compliance-pakke (GDPR, Datatilsynet, ENISA, ISO 27001/27701)

Dette er den dokumentation, en dataansvarlig, en databeskyttelsesrådgiver eller en revisor har brug for til at vurdere løsningen.
Teknik og dokumentation kan ikke alene give en *certificering*: ISO 27001/27701 certificerer en **organisation og dens ledelsessystem**,
udstedt af et akkrediteret certificeringsorgan efter audit. Løsningen er derfor bygget og dokumenteret, så den kan indgå i en sådan
certificering, men er **ikke certificeret** (se [`iso27001-roadmap.md`](iso27001-roadmap.md)).

| Dokument | Indhold |
|---|---|
| [`gdpr-checklist.md`](gdpr-checklist.md) | Artikel for artikel: krav, implementering, bevis, status |
| [`security-controls.md`](security-controls.md) | Datatilsynets katalog, ISO 27001:2022 Annex A, ENISA, OWASP ASVS → kontroller og status |
| [`pearson-benchmark.md`](pearson-benchmark.md) | Sammenligning med det niveau, Pearson Clinical offentligt oplyser, og hvad der mangler |
| [`iso27001-roadmap.md`](iso27001-roadmap.md) | Vej til ISO 27001 + 27701, penetrationstest, SOC 2-lignende rapportering |
| [`dpia.md`](dpia.md) | Tærskelvurdering og konsekvensanalyse (skabelon udfyldt med systemets risici) |
| [`ropa.md`](ropa.md) | Fortegnelser over behandlingsaktiviteter (art. 30) – dataansvarlig og databehandler |
| [`dpa-template.md`](dpa-template.md) | Databehandleraftale: bilag A–D, klar til udfyldning |
| [`incident-response.md`](incident-response.md) | Håndtering af brud (art. 33–34) og sikkerhedshændelser |
| [`retention-and-deletion.md`](retention-and-deletion.md) | Opbevarings- og sletteregler for alle datatyper inkl. backups |

## Statussymboler
✅ implementeret og afprøvet (kode/test nævnt) · 🟡 delvist, eller kræver en organisatorisk handling, som kun driftsansvarlig/dataansvarlig kan udføre · ⬜ mangler

## Før produktion – kort liste (det kode ikke kan gøre for dig)
1. Udfyld `OPERATOR_*`, `DPO_CONTACT`, `SECURITY_CONTACT`, `HOSTING_*` i `.env` (vises på `/privatliv/`, `/databehandling/`, `/cookies/`).
2. Underskriv databehandleraftaler: dataansvarlig ⇄ driftsansvarlig og driftsansvarlig ⇄ hostingudbyder ([`dpa-template.md`](dpa-template.md)).
3. Gennemfør tærskelvurdering/DPIA ([`dpia.md`](dpia.md)) og fastsæt retsgrundlag og opbevaringsperiode pr. dataansvarlig.
4. Verificér i driftsmiljøet: TLS 1.2+ i reverse proxy, ingen IP/cookies i proxy-log, krypterede diske, `HSTS_MAX_AGE` hævet, nøgler i managed secrets/KMS.
5. Planlæg krypteret backup (`scripts/backup.sh`) og test gendannelse.
6. Få udført ekstern penetrationstest og manuel skærmlæsertest.
7. Beslut om ISO 27001/27701-certificering skal opnås ([`iso27001-roadmap.md`](iso27001-roadmap.md)).

## Kilder (verificér altid mod den gældende udgave)
- GDPR (forordning 2016/679), især art. 5, 6, 7, 9, 11, 12–22, 24–25, 28, 30, 32–35.
- Datatilsynet: *Katalog over foranstaltninger* (udgivet nov. 2023, udvidet juni 2025), vejledning om databehandlere, brud, konsekvensanalyse og
  *Behandlingssikkerhed og databeskyttelse gennem design og standardindstillinger*; fælles vejledning om cookies fra Datatilsynet og Digitaliseringsstyrelsen (maj 2025).
- ENISA: *Pseudonymisation techniques and best practices* (2019); *Guidelines on shaping technology according to GDPR provisions*.
- ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO/IEC 27701; OWASP ASVS.
- Pearson Clinical: *Platform security & privacy* og *Q-global/Q-interactive privacy whitepaper* (offentlige sider/dokumenter).
