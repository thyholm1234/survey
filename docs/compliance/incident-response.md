# Håndtering af sikkerhedshændelser og brud på persondatasikkerheden

Mål: opdage, afgrænse, afhjælpe og dokumentere – og sikre, at den dataansvarlige kan underrette Datatilsynet **inden 72 timer** (art. 33) og de registrerede ved høj risiko (art. 34).
Databehandleren skal underrette den dataansvarlige **uden unødig forsinkelse** (art. 33, stk. 2; aftalt frist i DPA: senest [24] timer).

## Faser
| Fase | Handling | Værktøj/bevis |
|---|---|---|
| 1. Opdagelse | Alarmer (login-fejl, kæde-brud), kundens/forskers henvendelse (`SECURITY.md`), leverandørvarsel, CI-fund | Auditlog, `GET /api/admin/audit/verify`, rate-limit-poster |
| 2. Triage (inden 1 time) | Er personoplysninger berørt? Hvilke tenants? Fortrolighed/integritet/tilgængelighed? Notér tidspunkt for *konstatering* | Hændelseslog (skabelon nedenfor) |
| 3. Inddæmning | Deaktivér konti/koder (`disable`), tilbagekald sessioner, rotér hemmeligheder (`init-secrets.sh`), isolér container/netværk | Admin-API, docker |
| 4. Undersøgelse | Afgræns omfang via hash-kædet auditlog; verificér kæden; undersøg hosting-/proxy-logs; vurdér om data var krypterede | Auditlog |
| 5. Underretning | **Dataansvarlig** (altid, hurtigst muligt) → Datatilsynet (72 t, hvis risiko for de registrerede) → registrerede (hvis høj risiko). Brug Datatilsynets anmeldelsesblanket | Skabelon nedenfor |
| 6. Genopretning | Gendan fra krypteret backup, patch, verificér | `scripts/backup.sh`, CI |
| 7. Efterbehandling | Rod-årsagsanalyse, korrigerende handlinger, opdatér DPIA/risikoregister, indøv igen | Afvigelsesregister |

**Alle brud dokumenteres** (art. 33, stk. 5), også dem der ikke anmeldes.

## Skabelon til hændelsesregistrering
| Felt | |
|---|---|
| Hændelses-ID / konstateret (dato, tid, af hvem) | |
| Beskrivelse og type (fortrolighed / integritet / tilgængelighed) | |
| Berørte tenants, kategorier og omtrentligt antal registrerede og poster | |
| Var data krypterede / pseudonyme? (afgørende for risikovurdering) | |
| Sandsynlige konsekvenser for de registrerede | |
| Foranstaltninger truffet / foreslået | |
| Underrettet: dataansvarlig (tid) · Datatilsynet (tid/ikke nødvendig + begrundelse) · registrerede (tid/ikke nødvendig) | |
| Lærdom og korrigerende handlinger | |

## Roller
| Rolle | Ansvar |
|---|---|
| Hændelsesansvarlig (driftsansvarlig) | Leder forløbet, underretter dataansvarlig |
| Teknisk ansvarlig | Inddæmning, undersøgelse, genopretning |
| DPO/databeskyttelsesansvarlig | Rådgiver om anmeldelse og kommunikation |
| Dataansvarlig (kunde) | **Beslutter om og foretager anmeldelse til Datatilsynet og underretning af registrerede** |

## Øvelse
Indøv proceduren mindst én gang årligt (tabletop, fx »admin-konto kompromitteret« og »backup mistet«) og dokumentér resultatet.
