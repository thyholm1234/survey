# Databehandleraftale – udfyldningsskabelon (bilag A–D)

> **Brug Datatilsynets standardkontrakt som aftalens hovedtekst.** Datatilsynet har udarbejdet en standardkontrakt (databehandleraftale) efter art. 28, stk. 8, som er godkendt af EDPB, med bilag A–D.
> Download den seneste version fra datatilsynet.dk og indsæt klausulerne uændret; kun så er du sikker på, at aftalen lever op til art. 28. Teksten nedenfor udfylder **bilagene** for denne løsning. Den er ikke juridisk rådgivning.

Parter: **Dataansvarlig** [navn, CVR, adresse] · **Databehandler** [`OPERATOR_NAME`, CVR, adresse] · Kontaktperson/DPO: [..]

## Bilag A – Oplysninger om behandlingen
- **Formål:** drift og hosting af webbaseret spørgeskemaplatform til indsamling og aggregeret analyse af personalets besvarelser.
- **Karakter:** opbevaring, lagring, backup, sletning, generering af aggregerede resultater; support på instruks.
- **Typer af personoplysninger:** pseudonyme besvarelser; frivillige baggrundsvariable; tidsstempler og svartider; grov browser-/skærmklasse; administratorers brugernavn, adgangskode-hash, MFA-hemmelighed (krypteret), sessioner, logbog.
- **Kategorier af registrerede:** personale (respondenter), administratorer.
- **Varighed:** aftalens løbetid; rå besvarelser slettes automatisk efter dataansvarliges periode ([`retention-and-deletion.md`](retention-and-deletion.md)); ved ophør jf. klausul 11 i standardkontrakten: sletning efter udlevering.

## Bilag B – Underdatabehandlere
| Navn | CVR/org.nr. | Adresse | Behandling | Placering | Overførselsgrundlag |
|---|---|---|---|---|---|
| [`HOSTING_PROVIDER`] | | | Hosting af server og database | [`HOSTING_LOCATION`] (EU/EØS) | Ingen overførsel |

Dataansvarlig får **forudgående skriftlig varsel [30] dage** før tilføjelse/udskiftning, og kan gøre indsigelse.

## Bilag C – Instruks
- **Behandlingens genstand/instruks:** kun drift, support og sikkerhed; ingen anden brug; ingen kontakt til registrerede.
- **Sikkerhedsforanstaltninger (minimumskrav):** de, der er beskrevet i [`security-controls.md`](security-controls.md) og på `/databehandling/` (kryptering i transit/hvile, pseudonymisering, adgangsstyring med MFA, logning, adskillelse, automatisk sletning, krypteret backup, sårbarhedshåndtering, hændelsesprocedure). Databehandler skal ikke svække dem uden dataansvarliges samtykke.
- **Opbevaring og sletning:** jf. bilag A; slettede data kan findes i krypterede backups i højst [35] dage.
- **Lokalitet:** EU/EØS; ingen behandling i tredjelande, herunder fjernsupport.
- **Instruks om overførsel til tredjelande:** ingen.
- **Tilsyn/revision:** dataansvarlig kan årligt anmode om dokumentation (denne compliance-pakke, pentest-rapport, hostingudbyders certifikat) og gennemføre revision efter [14] dages varsel.
- **Brud:** underretning til dataansvarlig **uden unødig forsinkelse og senest [24] timer** efter konstatering ([`incident-response.md`](incident-response.md)).
- **Hjælp til registreredes rettigheder:** personlig kode-funktioner er indbygget; øvrige henvendelser videresendes til dataansvarlig inden [3] hverdage.

## Bilag D – Parternes regulering af andre forhold
[Ansvar, vederlag, kontaktpunkter, opsigelse, tilgængelighed/drift (SLA), RTO/RPO, rapportering. Udfyldes af parterne.]
