# Instrumentet: mestring og rammer i almenmiljøet

Instrumentet (`data/sample_almenramme_survey.json`, genereret af `scripts/build_sample_survey.py`)
måler, hvordan personale i skole og dagtilbud oplever konkrete adfærdsudtryk hos børn.

## Konstrukt: fire perspektiver

For hvert scenarie besvares fire udsagn (6-trins enig/uenig + *Kan ikke vurdere / har ikke oplevet*):

| Kode | Spørger til | Skelnen |
|---|---|---|
| `self` | Egen oplevelse af mestring | Selv-efficacy: ved *jeg*, hvad jeg kan gøre? |
| `team` | Fælles mestring | Kollektiv efficacy: handler *vi* sammen? |
| `frame` | Kan den **nuværende** ramme rumme det? | Faktisk kapacitet, som den er i dag |
| `expect` | Kan det **forventes** af en **almen** ramme? | Normativ vurdering, uafhængig af egen situation |

Forskellen mellem `frame` og `expect` er bærende: en medarbejder kan mene, at *deres* ramme ikke kan
rumme situationen (`frame` lav), men at det alligevel *bør* kunne forventes af en almen ramme
(`expect` høj) – eller omvendt. Gabet mellem de to er analytisk interessant, og derfor står `expect`
altid **sidst** (`fixedLastPerspective`): den normative vurdering må ikke farve de øvrige svar
(rækkefølgeeffekt, jf. Shaughnessy m.fl. kap. 5, Schuman m.fl. 1981).

`belong` (almen tilhørighed) fra den tidligere demo er stadig gyldig i schemaet, men bruges ikke i
dette instrument.

## 10 domæner × 3 adfærdsudtryk

Domænerne er **hverdagssituationer**, ikke symptomgrupper. Hvert har tre konkrete, observerbare
adfærdsbeskrivelser uden diagnosenavne. Tredjedelene dækker hver sin vanskelighedsprofil, men det
fremgår ikke for respondenten:

| Suffix i `scenarioId` | Adfærd tæt på | Eksempel |
|---|---|---|
| `_A` | opmærksomhed, aktivitets- og impulsregulering (ADHD-nær) | »Under en fælles samling rejser barnet sig og går rundt, mens de andre sidder.« |
| `_S` | socialt samspil, fleksibilitet og sanser (autisme-nær) | »Barnet vil kun løse opgaven på én bestemt måde og afviser den voksnes forslag.« |
| `_K` | sprogforståelse og sprogproduktion (sprog-nær) | »Barnet følger kun beskeder med ét led ad gangen og har brug for at få dem gentaget.« |

Domæner: FS fælles samling · SO selvstændigt arbejde · OV overgange · LE leg og samvær ·
KO konflikter og frustration · IN instruktioner · RU rutiner · SA støj og sanseindtryk ·
FO forandringer · UD selvudtryk.

Profilnøglen er et **analyseværktøj** (sammenlign mestring og rammeoplevelse på tværs af `_A/_S/_K`),
ikke en klassifikation af børn. Adfærd er ikke diagnose: samme adfærd ses ved mange baggrunde, og
ingen scenarier må bruges til at udpege eller vurdere enkeltbørn. Profilanalysen kræver at
profilen udledes af sidste tegn i `question_key` (fx `S_FS_A` → `A`) i eksporten; den er endnu ikke indbygget i appen.

## Hvad der blev ændret ift. DEMO-versionen, og hvorfor

Gennemgang mod Shaughnessy, Zechmeister & Zechmeister (2012), *Research Methods in Psychology*, kap. 5
(»Guidelines for the Effective Wording of Questions«, »Ordering of Questions«, trin 1–6 i
spørgeskemakonstruktion) og kap. 2 (reliabilitet og validitet):

| Problem i DEMO | Retningslinje | Rettelse |
|---|---|---|
| Beskrivelser med to adfærd (»græder eller råber«, »slår, sparker eller bider«) | Undgå double-barreled questions; omskriv til separate | Ét observerbart udtryk pr. scenarie |
| Rammeudsagn med fire ting (»tid, rum, personale og materialer«) | Samme | Defineres i instruktionen; udsagnet har ét budskab |
| Vage ord (»gentagne gange«, »få minutter«, »ofte«) | Vage ord tolkes forskelligt | Konkrete situationer; hyppighed fastsat i instruktionen (»flere gange om ugen«) |
| Ingen negativt formulerede items (`reverseScored` altid `false`) | Vend retningen på nogle items mod acquiescence/response set | 40 af 120 (10 pr. perspektiv) er semantisk modsat formuleret og reverse-scores; jævnt fordelt over domæner og adfærdstyper |
| »Naturlig del af fællesskabet« (følelsesladet/ledende) | Undgå leading og loaded questions | Perspektivet er erstattet af neutralt »hvad kan forventes« |
| Betingelse sidst i sætningen | Betinget information før hovedpointen | Betingelsen (»Når barnet viser denne adfærd, …«) står først |
| Udsagn > 20 ord | Højst ca. 20 ord | Maks. 20 ord pr. udsagn (kontrolleres af scriptet) |
| Alle respondenter tvinges til at svare | Respondenter svarer også på spørgsmål uden gyldigt svar | `Kan ikke vurdere / har ikke oplevet` er missing, aldrig midtpunkt |
| Begreber som »ramme«, »almen« uforklaret | Begreber fortolkes ud fra egen kultur | Defineret i hvert perspektivs instruktion (almen = almindelig normering, ingen ekstra ressourcer) |
| 40 scenarier × 4 = 160 spørgsmål | Hold spørgeskemaet så kort som muligt | 30 scenarier × 4 = 120 spørgsmål (skønnet ca. 20 min; skal måles i pretest). De fire udsagnsskabeloner er bevidst ens på tværs af scenarier, så perspektiverne kan sammenlignes |

### Social desirability

Bogen peger på at selvrapportering er reaktiv: personale vil svare, som de »bør«. Det er særligt
udtalt her, fordi »jeg ved, hvad jeg skal gøre« og »vi kan rumme det« er professionelt ladede.
Modforanstaltninger i designet: pseudonymitet, celleundertrykkelse (n ≥ 10), negativt formulerede
items, normative udsagn adskilt (`expect`) og eksplicit tilladelse til at vælge *Kan ikke vurdere*.
Resultater skal derfor fortolkes som **oplevelse**, ikke som faktisk kompetence eller kapacitet.

## Bogens seks trin: status

1. **Hvad skal vides** – fire konstrukter, ti domæner, tre vanskelighedsprofiler. Analyseplan: `docs/analysis-protocol.md` (skrevet før dataindsamling, som bogen anbefaler).
2. **Administration** – selvadministreret webskema. Bogen anbefaler at genbruge validerede instrumenter, hvor de findes; om et sådant findes på dansk til dette formål, er ikke undersøgt her.
3. **Første udkast** – genereret af scriptet.
4. **Gennemgang** – ✅ efter retningslinjerne (mekanisk lint). ⬜ **Mangler:** faglig gennemgang af repræsentanter fra både skole og dagtilbud samt PPR/sprog-/specialpædagogisk fagperson, og af en der er skeptisk over for »almen ramme« som begreb (bogens råd om at lade repræsentanter fra flere synspunkter se efter ledende ord).
5. **Pretest** – ⬜ **Mangler (bogens vigtigste trin).** Prøv med 8–12 medarbejdere fra begge typer institutioner under realistiske forhold, og interview dem bagefter om hvert scenarie: Er adfærden genkendelig? Forstår de forskellen på `frame` og `expect`? Hvilke scenarier er uklare? Tilpas og pretest igen ved større ændringer.
6. **Endelig redigering og procedure** – afhænger af trin 5.

## Reliabilitet og validitet: hvad skal påvises

Instrumentet er **ikke valideret**. Appens analysemodul giver cronbachs alfa, omega, item-total m.m. pr.
perspektiv (se analyseprotokollen), men det er kun *intern konsistens*. Bogens begreber, anvendt her:

- **Indholdsvaliditet** – dækker scenarierne reelt de adfærdsudtryk, personale møder? (ekspertgennemgang)
- **Konstruktvaliditet** – hænger `self` og `team` sammen (konvergent), men adskiller sig fra `frame`/`expect` (diskriminant)? Forventning: `self`–`team` korrelerer højest. Hvis `frame` og `expect` ikke kan adskilles empirisk, bør de slås sammen.
- **Reliabilitet** – intern konsistens (alfa/omega) pr. perspektiv; test–retest på en delmængde (fx 3–4 uger) er endnu ikke understøttet i appen.
- **Retningseffekt** – negativt formulerede items kan danne en egen faktor. Kontrollér det i en følsomhedsanalyse (med/uden reverse-items).
- **Adfærd er ikke tilstand** – scenarierne er adskilte; der er ikke teoretisk grund til at forvente ensartet mestring på tværs af `_A/_S/_K`. Rapportér derfor både perspektivscore og profilscore, og undgå en totalscore.
