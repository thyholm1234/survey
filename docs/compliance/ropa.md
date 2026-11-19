# Fortegnelser over behandlingsaktiviteter (art. 30)

## A. Databehandlerens fortegnelse (art. 30, stk. 2) – driftsansvarlig
| Felt | Indhold |
|---|---|
| Databehandler / kontakt / DPO | Se `.env` (`OPERATOR_*`, `DPO_CONTACT`) |
| Dataansvarlige, på hvis vegne der behandles | Pr. tenant (kunde) – oplistes i kundekartotek |
| Kategorier af behandling | Hosting, drift, backup, support af spørgeskemaplatform; indsamling og opbevaring af pseudonyme besvarelser; generering af aggregerede resultater |
| Tredjelandsoverførsler | Ingen |
| Tekniske/organisatoriske foranstaltninger | [`security-controls.md`](security-controls.md), `/databehandling/` |

## B. Dataansvarliges fortegnelse (art. 30, stk. 1) – skabelon til kunden
| Felt | Udfyldt for dette instrument |
|---|---|
| Formål | Undersøge personales oplevelse af mestring, fælles mestring, rammernes kapacitet og forventninger til en almen ramme, med henblik på praksisudvikling |
| Retsgrundlag | *Kunden vælger:* art. 6(1)(e) (myndighedsopgave) / (a) samtykke / (f) legitim interesse. Se bemærkning i [`dpia.md`](dpia.md) |
| Kategorier af registrerede | Personale i skole og dagtilbud; administratorer |
| Kategorier af personoplysninger | Pseudonyme besvarelser; frivillige baggrundsvariable (faggruppe, anciennitet, specialpædagogisk uddannelse, arbejdsområde); tidsstempler/svartider; grov browser-/skærmklasse; administratorers brugernavn og logbog. **Ingen** art. 9-oplysninger |
| Modtagere | Dataansvarlig (aggregeret); databehandler; underdatabehandler (hosting) |
| Overførsel til tredjeland | Ingen |
| Slettefrister | Rå besvarelser: kundens periode (standard 24 mdr.); logbog: se [`retention-and-deletion.md`](retention-and-deletion.md) |
| Sikkerhedsforanstaltninger | Se `security-controls.md` |
| Kilde | Direkte fra den registrerede |
| Konsekvensanalyse | [`dpia.md`](dpia.md) |
