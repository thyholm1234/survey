# Sikkerhedspolitik

## Meld en sårbarhed
Opdager du en sårbarhed, så **offentliggør den ikke**. Brug GitHubs *Private vulnerability reporting*
(fanen *Security* → *Report a vulnerability*) eller kontakt driftsansvarlig (se `/databehandling/`).
Vi bekræfter modtagelse inden for 3 hverdage og vurderer og udbedrer efter alvor. Følg ikke selv op med
test mod produktionsdata.

## Understøttede versioner
Kun seneste udgivelse på `main` får sikkerhedsrettelser.

## Hvad vi gør løbende
Ugentlig automatisk kontrol af afhængigheder (pip-audit), statisk analyse (Bandit), hemmelighedsscanning
(gitleaks) og container-scan (Trivy), samt Dependabot-opdateringer. Se `docs/compliance/`.

## Persondata-brud
Mistanke om brud på persondatasikkerheden håndteres efter `docs/compliance/incident-response.md`
(underretning af den dataansvarlige uden unødig forsinkelse, så 72-timersfristen i GDPR art. 33 kan overholdes).
