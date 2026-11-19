# Vej til ISO/IEC 27001 og 27701 (og anden verificering)

**Hvad en certificering er.** ISO 27001 certificerer et *ledelsessystem for informationssikkerhed (ISMS)* i en organisation – ikke et stykke software. ISO 27701 udvider med privatlivsstyring (PIMS) og
er velegnet til en databehandler. Certifikatet udstedes af et akkrediteret organ (i Danmark fx via DANAK-akkrediterede organer) efter en to-trins audit og gælder tre år med årlige overvågningsaudits.
Løsningens kontroller ([`security-controls.md`](security-controls.md)) dækker de tekniske Annex A-kontroller; ledelseslaget skal opbygges af den driftsansvarlige organisation.

## Trin
| # | Aktivitet | Output | Ansvar |
|---|---|---|---|
| 1 | Fastlæg **scope** (tjenesten, driftsmiljø, personer, lokationer) og kontekst (interessenter, krav: GDPR, kunder) | Scope-erklæring (klausul 4) | Ledelse |
| 2 | **Ledelsens forpligtelse**, informationssikkerhedspolitik, roller (CISO/DPO), mål | Politik, rolle-/ansvarsbeskrivelser (klausul 5) | Ledelse |
| 3 | **Risikovurdering og -håndtering** (metode, risikoregister, risikoejere) – genbrug trusselsmodellen (`docs/threat-model.md`) og DPIA | Risikometode, register, handlingsplan (klausul 6) | CISO |
| 4 | **Statement of Applicability (SoA)**: alle 93 Annex A-kontroller, anvendelig ja/nej, begrundelse, status | SoA – start fra tabellen i `security-controls.md` | CISO |
| 5 | Organisatoriske kontroller: leverandørstyring, adgangsreview (kvartalsvis), onboarding/offboarding, **awareness-uddannelse**, ændringsstyring, backup/gendannelsestest, hændelsesøvelse, kontinuitet | Procedurer + **beviser** (logs, referater) | Drift/HR |
| 6 | **Overvågning**: central log, alarmer, sårbarhedsscanning (CI findes) | SIEM/alarmregler, scanrapporter (klausul 9.1) | Drift |
| 7 | **Ekstern penetrationstest** af web, API og drift; remediering | Rapport + lukkede fund | Ekstern |
| 8 | **Intern audit** + **ledelsens gennemgang** | Auditrapport, referat (klausul 9.2–9.3) | Intern/ledelse |
| 9 | Korrigerende handlinger, løbende forbedring | Afvigelsesregister (klausul 10) | CISO |
| 10 | **Certificeringsaudit** (trin 1 dokumentgennemgang, trin 2 implementering) | Certifikat | Certificeringsorgan |
| 11 | ISO 27701: udvid med PIMS (art. 28-kontroller for databehandler; ROPA, rettighedsprocesser, brudprocesser) | Udvidet SoA | DPO |

## Realistisk tidsramme
For en lille organisation med færdig teknisk platform: 4–9 måneder til certificering, hvoraf mindst 3 måneder skal gå med at generere *beviser* på, at processerne faktisk kører (auditor kræver driftsdata).

## Supplerende, ofte efterspurgt verificering
- **Pentest** (årligt og efter større ændringer).
- **ISAE 3402 / SOC 2 Type II**-lignende erklæring (revisor) – efterspørges af kommuner/regioner som tillid til databehandlere.
- **Tilgængelighedserklæring** og ekstern WCAG-audit (for offentlige kunder).
- **Cyber Essentials/NIS2**: afhænger af kundens sektor og organisationens størrelse; vurdér om kunden som væsentlig/vigtig enhed stiller krav til leverandører.
- **Hostingudbyderens** ISO 27001/SOC 2-dokumentation indhentes og arkiveres (leverandørstyring A.5.19–5.23).

## Hvad jeg bevidst ikke gør
Jeg påstår ikke at være certificeret, og de offentlige sider siger det udtrykkeligt (`/databehandling/`). Et certifikat kan ikke købes, kopieres eller erstattes af denne dokumentation.
