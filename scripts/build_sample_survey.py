#!/usr/bin/env python3
"""Genererer data/sample_almenramme_survey.json.

BEMÆRK: Specifikationens bilag `sample_almenramme_survey.json` var ikke vedlagt.
Denne fil er en strukturelt tro DEMO-rekonstruktion (40 adfærdsbeskrivelser,
10 domæner, 4 perspektiver = 160 spørgsmål). Ordlyden er ikke valideret og
skal erstattes af det rigtige instrument før reel brug.
"""
import json
import pathlib

DOMAINS = [
    ("OA", "Opmærksomhed og aktivitetsregulering", [
        "Barnet rejser sig gentagne gange under en fælles samling og går rundt i rummet.",
        "Barnet skifter aktivitet efter få minutter og efterlader det påbegyndte.",
        "Barnet taler eller råber ind i andres tale under en fælles aktivitet.",
        "Barnet ser ud til ikke at opfatte en kollektiv besked og fortsætter sin aktivitet.",
    ]),
    ("ER", "Følelsesmæssig regulering", [
        "Barnet græder eller råber længe, når en leg eller aktivitet slutter.",
        "Barnet bliver hurtigt vredt, når noget ikke lykkes, og kaster med materialer.",
        "Barnet har svært ved at falde til ro igen efter en konflikt.",
        "Barnet reagerer kraftigt på små ændringer i stemningen i gruppen.",
    ]),
    ("SI", "Socialt samspil og leg", [
        "Barnet står ved siden af andres leg uden at komme ind i den.",
        "Barnet overtager legen og bestemmer reglerne uden at lytte til de andre.",
        "Barnet trækker sig, når andre børn tager kontakt.",
        "Barnet misforstår ofte andre børns signaler og invitationer.",
    ]),
    ("KO", "Kommunikation og sprog", [
        "Barnet bruger få ord og peger eller trækker i den voksne for at vise, hvad det vil.",
        "Barnet svarer ikke, når det bliver spurgt direkte i en gruppe.",
        "Barnet gentager ord eller sætninger uden tydelig sammenhæng med situationen.",
        "Barnet har svært ved at fortælle, hvad der er sket i en konflikt.",
    ]),
    ("SE", "Sansebearbejdning", [
        "Barnet holder sig for ørerne eller forlader rummet, når der er larm.",
        "Barnet søger meget fysisk kontakt, fx skubber, krammer hårdt eller kravler.",
        "Barnet undgår bestemte materialer, tøj eller madkonsistenser.",
        "Barnet virker uopmærksomt på smerte, kulde eller varme.",
    ]),
    ("FL", "Fleksibilitet og overgange", [
        "Barnet protesterer kraftigt, når dagens plan ændres.",
        "Barnet har svært ved at stoppe en aktivitet for at gå videre til den næste.",
        "Barnet insisterer på at gøre tingene på en bestemt måde eller i en bestemt rækkefølge.",
        "Barnet bliver uroligt ved ankomst og afhentning.",
    ]),
    ("EF", "Igangsætning og organisering", [
        "Barnet går ikke i gang med en opgave, selvom det har fået en instruktion.",
        "Barnet mister overblikket over flere trin i en opgave.",
        "Barnet glemmer ofte sine ting eller ved ikke, hvor de er.",
        "Barnet har svært ved at vente på tur.",
    ]),
    ("MO", "Motorik og kropslig regulering", [
        "Barnet falder eller støder ofte ind i ting og andre.",
        "Barnet undgår aktiviteter med blyant, saks eller små materialer.",
        "Barnet bevæger sig næsten konstant, også under stillesiddende aktiviteter.",
        "Barnet bliver hurtigt træt i kroppen og lægger sig ned under aktiviteter.",
    ]),
    ("KA", "Konflikter og udadreagerende adfærd", [
        "Barnet slår, sparker eller bider, når det bliver frustreret.",
        "Barnet siger nej til de fleste voksenforslag og forhandler længe.",
        "Barnet ødelægger andres ting eller byggerier.",
        "Barnet bruger grimme ord eller trusler over for andre.",
    ]),
    ("TA", "Tilbagetrækning og bekymring", [
        "Barnet sidder ofte alene og deltager ikke i fælles aktiviteter.",
        "Barnet spørger mange gange om det samme for at være sikker.",
        "Barnet klager over ondt i maven eller hovedet før bestemte aktiviteter.",
        "Barnet virker anspændt og stille i nye situationer.",
    ]),
]

QUESTION_TEMPLATES = {
    "self": "I en situation som denne ved jeg, hvad jeg kan gøre for at støtte barnets deltagelse.",
    "team": "I vores team har vi en fælles praksis for at støtte barnet i en situation som denne.",
    "frame": "Vores rammer (tid, rum, personale og materialer) gør det muligt at støtte barnet i en situation som denne.",
    "belong": "Et barn, der viser denne adfærd, er en naturlig del af fællesskabet hos os.",
}
PREFIX = {"self": "S", "team": "T", "frame": "F", "belong": "B"}

survey = {
    "schemaVersion": "1.0.0",
    "surveyId": "almenramme",
    "title": "Mestring og tilhørighed i almenmiljøet (DEMO)",
    "language": "da",
    "description": "DEMO-rekonstruktion. Ikke valideret instrument.",
    "responseScale": {
        "type": "likert",
        "min": 1,
        "max": 6,
        "labels": [
            {"value": 1, "label": "Helt uenig"},
            {"value": 2, "label": "Uenig"},
            {"value": 3, "label": "Lidt uenig"},
            {"value": 4, "label": "Lidt enig"},
            {"value": 5, "label": "Enig"},
            {"value": 6, "label": "Helt enig"},
        ],
        "cannotAssess": {"code": "CANNOT_ASSESS", "label": "Kan ikke vurdere"},
    },
    "perspectives": [
        {"code": "self", "name": "Min egen mestring",
         "instruction": "Vurdér her din egen mulighed for at handle i situationen."},
        {"code": "team", "name": "Teamets fælles mestring",
         "instruction": "Vurdér her dit teams fælles mulighed for at handle i situationen."},
        {"code": "frame", "name": "Rammens kapacitet",
         "instruction": "Vurdér her, om rammerne gør det muligt at handle i situationen."},
        {"code": "belong", "name": "Almen tilhørighed",
         "instruction": "Vurdér her, om et barn med denne adfærd hører til i fællesskabet."},
    ],
    "fixedLastPerspective": "belong",
    "domains": [{"code": c, "name": n} for c, n, _ in DOMAINS],
    "backgroundVariables": [
        {"code": "profession", "label": "Faggruppe", "options": [
            {"code": "paedagog", "label": "Pædagog"},
            {"code": "paed_assistent", "label": "Pædagogisk assistent/medhjælper"},
            {"code": "laerer", "label": "Lærer"},
            {"code": "leder", "label": "Leder"},
            {"code": "andet", "label": "Andet"}]},
        {"code": "experience", "label": "Anciennitet i faget", "options": [
            {"code": "0-2", "label": "0–2 år"},
            {"code": "3-5", "label": "3–5 år"},
            {"code": "6-10", "label": "6–10 år"},
            {"code": "11plus", "label": "11 år eller mere"}]},
        {"code": "special_training", "label": "Specialpædagogisk efteruddannelse", "options": [
            {"code": "yes", "label": "Ja"},
            {"code": "no", "label": "Nej"}]},
        {"code": "work_area", "label": "Primært arbejdsområde", "options": [
            {"code": "0-2", "label": "Børn 0–2 år"},
            {"code": "3-5", "label": "Børn 3–5 år"},
            {"code": "indskoling", "label": "Indskoling"},
            {"code": "mellemtrin", "label": "Mellemtrin"},
            {"code": "udskoling", "label": "Udskoling"},
            {"code": "sfo", "label": "SFO/fritid"}]},
    ],
    "respondentInfo": {
        "purpose": "Undersøgelsen belyser, hvordan medarbejdere oplever egen og teamets mestring, rammernes kapacitet og børns tilhørighed i almenmiljøet. Resultaterne bruges udelukkende samlet til udvikling af praksis.",
        "voluntary": "Det er frivilligt at deltage, og du kan springe spørgsmål over eller stoppe når som helst.",
        "dataController": "[Indsæt dataansvarlig myndighed]",
        "retention": "Rå besvarelser opbevares i op til 24 måneder og slettes derefter. Samlede resultater kan opbevares længere.",
        "contact": "[Indsæt kontakt / databeskyttelsesrådgiver]",
        "pseudonymity": "Vi indsamler ikke navn, e-mail, CPR-nummer eller IP-adresse sammen med dine svar. Resultater vises kun for grupper over en minimumsstørrelse.",
    },
    "items": [],
}

for code, _name, behaviors in DOMAINS:
    for i, behavior in enumerate(behaviors, start=1):
        sid = f"{code}{i:02d}"
        survey["items"].append({
            "scenarioId": sid,
            "domainCode": code,
            "behavior": behavior,
            "questions": [
                {"id": f"{PREFIX[p]}_{sid}", "perspective": p, "text": t, "reverseScored": False}
                for p, t in QUESTION_TEMPLATES.items()
            ],
        })

out = pathlib.Path(__file__).resolve().parent.parent / "data" / "sample_almenramme_survey.json"
out.write_text(json.dumps(survey, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Skrev {out} ({len(survey['items'])} items, {sum(len(i['questions']) for i in survey['items'])} spørgsmål)")
