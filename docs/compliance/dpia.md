# Konsekvensanalyse (DPIA) – tærskelvurdering og risikodel

> Skabelon udfyldt med de forhold, der er kendt fra løsningen. **Den dataansvarlige** skal tilpasse, godkende og underskrive.
> Datatilsynet har en liste over behandlinger, der altid kræver DPIA, og en vejledning om konsekvensanalyse; tjek den gældende version.

## 1. Tærskelvurdering (art. 35, stk. 3 og Datatilsynets liste)
| Spørgsmål | Svar for dette instrument | Begrundelse |
|---|---|---|
| Særlige kategorier (art. 9) i stort omfang? | **Nej** | Respondenterne er personale; spørgsmålene handler om arbejdsoplevelser. Ingen helbreds-, diagnose- eller børneoplysninger |
| Børns oplysninger? | Nej | Scenarier beskriver adfærdstyper, ikke enkeltbørn; ingen navne/fritekst |
| Systematisk og omfattende vurdering/profilering med retsvirkning? | Nej | Kun gruppe-aggregater (n ≥ 10); ingen individprofiler eller afgørelser |
| Systematisk overvågning af ansatte? | **Vurdér** | Frivillig survey, men arbejdsgiver ⇄ ansat er et ubalanceret forhold. Kombination med små teams kan give re-identifikationsrisiko |
| Sårbare registrerede (ansatte)? | **Ja, i princippet** (EDPB: ansatte er sårbare pga. ubalance) | Mitigeres af pseudonymitet, frivillighed, k-anonymitet |
| Nye teknologier / sammenkobling af datasæt? | Nej | |
| Stort omfang? | Afhænger af kunden | |

**Anbefaling:** gennemfør en fuld DPIA, når (a) instrumentet ændres til at indeholde helbredsdata, (b) grupper under 10 personer rapporteres, eller (c) resultater bruges til personaleledelse. For det aktuelle instrument og med k ≥ 10 er en *dokumenteret tærskelvurdering med risikovurdering* som minimum nødvendig; de fleste offentlige dataansvarlige vælger at lave en fuld DPIA af forsigtighed. Nedenfor er risikodelen færdig.

## 2. Beskrivelse af behandlingen
Se [`ropa.md`](ropa.md) (formål, kategorier, modtagere, opbevaring) og `/databehandling/`.
**Nødvendighed og proportionalitet:** formålet (udvikling af praksis) kan ikke opnås med færre data; ingen identifikatorer indsamles; deltagelse er frivillig; svar kan slettes.

## 3. Risikovurdering (sandsynlighed × konsekvens for de registrerede)
| # | Risiko for de registrerede | Før | Foranstaltninger | Efter |
|---|---|---|---|---|
| R1 | **Re-identifikation** i små grupper (kolleger kan gætte hvem der har svaret) | Høj | k ≥ 10, sekundær undertrykkelse, komplementregel, rækkeeksport kun for autoriserede og kun n ≥ k, baggrundsvariable frivillige og få | Lav–middel (rest: differencing over tid, kvasi-identifikatorer i rækkeeksport) |
| R2 | **Pres/repressalier** på grund af svar (ansatte frygter konsekvenser) | Høj | Pseudonymitet, frivillighed, ingen individ-visning, ingen ranglister, retsgrundlag og formål oplyst, klar besked om at resultater ikke bruges individuelt | Lav–middel (kræver ledelsesløfte) |
| R3 | **Uautoriseret adgang/datalæk** | Middel | Kryptering, adskilte databaser, MFA, minimale rettigheder, hash-kædet log, CSP, pentest (mangler) | Lav |
| R4 | **Manglende udøvelse af rettigheder** | Middel | Personlig kode; eksport/sletning (testet); oplysning om at tabt kode betyder, at besvarelsen ikke kan findes | Lav |
| R5 | **Brug til andet formål** (fx personalesager) | Middel | Formålsbegrænsning i instruks/DPA; ingen rækkeeksport uden ret; audit af eksport | Lav–middel |
| R6 | **Backups bevarer slettede data** | Lav–middel | Rotation (35 dage), krypterede, oplyst ved sletning | Lav |
| R7 | **Tredjelandsoverførsel** | Lav | Kun EU/EØS; ingen tredjepartsressourcer | Meget lav |
| R8 | **Administratorkonto kompromitteres** | Middel | Obligatorisk MFA, rate limit, kontolås, kort session, audit | Lav |

## 4. Konklusion og godkendelse
Restrisici: R1/R2/R5 afhænger af kundens brug og kræver ledelsesbeslutning. Hvis restrisikoen vurderes høj uden mulighed for afhjælpning → **forudgående høring af Datatilsynet (art. 36)**.

| Dataansvarlig | DPO-udtalelse | Godkendt af | Dato | Næste revurdering |
|---|---|---|---|---|
| | | | | (senest 12 mdr. eller ved ændring) |
