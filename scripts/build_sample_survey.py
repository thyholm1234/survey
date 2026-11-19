#!/usr/bin/env python3
"""Genererer data/sample_almenramme_survey.json.

Instrument: personalets oplevelse af egen mestring, teamets fælles mestring, rammens kapacitet og
om det kan forventes af en almen ramme – på tværs af 10 situationsdomæner. Hvert domæne har tre
konkrete adfærdsbeskrivelser (ingen diagnoser) der spænder over opmærksomheds-/aktivitets-,
social/fleksibilitets- og sprogrelaterede vanskeligheder. 30 scenarier x 4 perspektiver = 120 spørgsmål.

Ordlyden er udarbejdet efter retningslinjerne i Shaughnessy, Zechmeister & Zechmeister (2012),
kap. 5, men er IKKE pilottestet. Se docs/instrument.md og gennemfør pretest (trin 5) før reel brug.
Kør: python3 scripts/build_sample_survey.py   (skriver og lint'er filen)
"""
import json
import pathlib

# ---------------------------------------------------------------------------
# 10 situationsdomæner x 3 adfærdsbeskrivelser = 30 scenarier.
# Hvert scenarie er ét konkret, observerbart udtryk for adfærd – ingen diagnosenavne.
# Nøglen til analyse (skjult for respondenten, kun i scenarioId-suffikset):
#   _A = adfærd tæt på opmærksomheds-/aktivitets-/impulsregulering   (ADHD-nær)
#   _S = adfærd tæt på socialt samspil, fleksibilitet og sanser       (autisme-nær)
#   _K = adfærd tæt på sprogforståelse og sprogproduktion             (sprog-nær)
# Se docs/instrument.md for begrundelse og analysebrug.
# ---------------------------------------------------------------------------
CLUSTERS = ["A", "S", "K"]

DOMAINS = [
    ("FS", "Fælles samling og undervisning", [
        "Under en fælles samling rejser barnet sig og går rundt, mens de andre sidder.",
        "Under en fælles samling sætter barnet sig kun på sin faste plads og bliver urolig, hvis den er optaget.",
        "Når barnet bliver spurgt under en fælles samling, svarer det kun med enkeltord eller peger.",
    ]),
    ("SO", "Selvstændigt arbejde og opgaveløsning", [
        "Barnet forlader sin opgave, før den er færdig, og går i gang med noget andet.",
        "Barnet vil kun løse opgaven på én bestemt måde og afviser den voksnes forslag.",
        "Barnet sidder med en opgave, det tydeligvis ikke forstår, men beder ikke om hjælp.",
    ]),
    ("OV", "Overgange og skift mellem aktiviteter", [
        "Ved skift mellem aktiviteter glemmer barnet sine ting og kommer sidst afsted.",
        "Når en aktivitet slutter, nægter barnet at stoppe og protesterer højlydt.",
        "Ved skift mellem aktiviteter overhører barnet beskeden og bliver stående, til en voksen henvender sig direkte.",
    ]),
    ("LE", "Leg og samvær med andre børn", [
        "I legen tager barnet legetøj eller springer ind i legen, før det er barnets tur.",
        "Barnet leger ved siden af de andre børn, men ikke sammen med dem, selv når de inviterer.",
        "I legen kan barnet ikke få de andre til at forstå, hvad det vil, og legen går i stå.",
    ]),
    ("KO", "Konflikter og frustration", [
        "Når barnet bliver irriteret, skubber eller råber det med det samme, før det har tænkt sig om.",
        "Når et andet barn bryder en regel, bliver barnet stærkt oprevet og kan ikke give slip på det.",
        "Efter en konflikt kan barnet ikke fortælle den voksne, hvad der skete.",
    ]),
    ("IN", "Instruktioner og beskeder fra voksne", [
        "Barnet går i gang, før instruktionen er givet færdig, og springer trin over.",
        "Barnet tager talemåder og spøg bogstaveligt og bliver forvirret.",
        "Barnet følger kun beskeder med ét led ad gangen og har brug for at få dem gentaget.",
    ]),
    ("RU", "Rutiner og praktiske situationer", [
        "I en rutine som af- og påklædning glemmer barnet næste skridt og bliver midt i den.",
        "Barnet vil have maden, pladsen eller rækkefølgen på samme måde hver gang og afviser alternativer.",
        "Barnet kan ikke sige, hvad det har brug for ved spisning eller toiletbesøg, og bliver urolig.",
    ]),
    ("SA", "Støj, uro og sanseindtryk i miljøet", [
        "Når der er uro i lokalet, bliver barnet opslugt af de andres aktivitet og mister sin egen opgave.",
        "Ved høje lyde holder barnet sig for ørerne eller forlader rummet.",
        "Når flere taler samtidig, kan barnet ikke følge med i, hvad der bliver sagt.",
    ]),
    ("FO", "Forandringer og det uventede", [
        "Når noget spændende sker, forlader barnet den aftalte aktivitet og følger det i stedet.",
        "Når en vikar kommer, eller planen ændres, bliver barnet så urolig, at det ikke kan deltage.",
        "Barnet har brug for billeder eller fagter for at forstå, at dagens plan er ændret.",
    ]),
    ("UD", "Selvudtryk og at blive forstået", [
        "Barnet råber svaret ud eller taler i munden på andre, før det har fået ordet.",
        "Barnet fortæller detaljeret om sit eget emne og lægger ikke mærke til, at lytteren mister interessen.",
        "Barnet leder efter ord og opgiver at fortælle, når de andre ikke forstår det.",
    ]),
]

# Fire perspektiver = fire spørgsmål pr. scenarie. Hvert har en positivt og en negativt
# formuleret variant (semantisk modsatrettet, ikke blot indsat "ikke"). Betingelsen står først,
# og ingen sætning har mere end ét budskab (Shaughnessy et al., kap. 5).
QUESTION_TEXTS = {
    "self": (
        "Når barnet viser denne adfærd, ved jeg, hvad jeg kan gøre for at hjælpe barnet videre.",
        "Når barnet viser denne adfærd, er jeg usikker på, hvad jeg skal gøre.",
    ),
    "team": (
        "Når barnet viser denne adfærd, handler vi i teamet ud fra en fælles tilgang.",
        "Når barnet viser denne adfærd, kan vi i teamet ikke blive enige om, hvad vi skal gøre.",
    ),
    "frame": (
        "Med de nuværende rammer hos os kan vi rumme barnet, når det viser denne adfærd.",
        "Når barnet viser denne adfærd, sprænger det de nuværende rammer hos os.",
    ),
    "expect": (
        "Det kan med rimelighed forventes, at en almen ramme kan rumme barnet, når det viser denne adfærd.",
        "Når barnet viser denne adfærd, kræver det mere, end man med rimelighed kan forvente af en almen ramme.",
    ),
}
PREFIX = {"self": "S", "team": "T", "frame": "F", "expect": "E"}
PERSP_ORDER = list(QUESTION_TEXTS)


def is_reversed(domain_idx: int, cluster_idx: int, persp_idx: int) -> bool:
    """Deterministisk, ca. 1/3 negativt formulerede; fordeler sig jævnt på domæner og adfærdstyper
    (så retning ikke er sammenfaldende med en bestemt adfærdstype eller et bestemt domæne)."""
    return (domain_idx + cluster_idx + persp_idx) % 3 == 0


survey = {
    "schemaVersion": "1.0.0",
    "surveyId": "almenramme",
    "title": "Mestring og rammer i almenmiljøet",
    "language": "da",
    "description": "Spørgeskemaet beskriver konkrete situationer med børn i hverdagen. For hver situation bedes du vurdere din egen og teamets mestring, om de nuværende rammer kan rumme situationen, og om det kan forventes af en almen ramme. Vi spørger til adfærd, ikke til bestemte børn eller diagnoser. Der er ingen rigtige eller forkerte svar. Hvis du ikke har oplevet adfærden, eller ikke kan vurdere den, vælg Kan ikke vurdere.",
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
        "cannotAssess": {"code": "CANNOT_ASSESS", "label": "Kan ikke vurdere / har ikke oplevet"},
    },
    "perspectives": [
        {"code": "self", "name": "Min egen mestring",
         "instruction": "Vurdér din egen mulighed for at handle, når du står i situationen. Tænk på adfærd, der optræder flere gange om ugen."},
        {"code": "team", "name": "Teamets fælles mestring",
         "instruction": "Vurdér det team, du arbejder sammen med omkring børnene (kolleger i stuen, klassen eller årgangen)."},
        {"code": "frame", "name": "Den nuværende rammes kapacitet",
         "instruction": "Ramme betyder tid, antal voksne, rum og materialer, som de er hos jer i dag. Vurdér, om jeres nuværende ramme kan rumme situationen."},
        {"code": "expect", "name": "Hvad kan forventes af en almen ramme",
         "instruction": "En almen ramme er en almindelig stue eller klasse med almindelig normering, uden ekstra ressourcer eller særlig støtte. Vurdér, hvad der med rimelighed kan forventes af en sådan ramme – uanset hvordan det ser ud hos jer."},
    ],
    "fixedLastPerspective": "expect",
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
        "purpose": "Undersøgelsen belyser, hvordan personale i skole og dagtilbud oplever deres egen og teamets mestring, om de nuværende rammer kan rumme konkrete situationer, og hvad der med rimelighed kan forventes af en almen ramme. Vi spørger til adfærd, ikke til bestemte børn eller diagnoser. Resultaterne bruges udelukkende samlet til udvikling af praksis.",
        "voluntary": "Det er frivilligt at deltage, og du kan springe spørgsmål over eller stoppe når som helst.",
        "dataController": "[Indsæt dataansvarlig myndighed]",
        "retention": "Rå besvarelser opbevares i op til 24 måneder og slettes derefter. Samlede resultater kan opbevares længere.",
        "contact": "[Indsæt kontakt / databeskyttelsesrådgiver]",
        "pseudonymity": "Vi indsamler ikke navn, e-mail, CPR-nummer eller IP-adresse sammen med dine svar. Resultater vises kun for grupper over en minimumsstørrelse.",
    },
    "items": [],
}

for d_idx, (code, _name, behaviors) in enumerate(DOMAINS):
    assert len(behaviors) == len(CLUSTERS)
    for c_idx, (cluster, behavior) in enumerate(zip(CLUSTERS, behaviors)):
        sid = f"{code}_{cluster}"
        questions = []
        for p_idx, p in enumerate(PERSP_ORDER):
            rev = is_reversed(d_idx, c_idx, p_idx)
            questions.append({"id": f"{PREFIX[p]}_{sid}", "perspective": p,
                              "text": QUESTION_TEXTS[p][1 if rev else 0], "reverseScored": rev})
        survey["items"].append({"scenarioId": sid, "domainCode": code, "behavior": behavior,
                                "questions": questions})


def lint(doc: dict) -> list[str]:
    """Mekanisk kontrol af retningslinjerne fra kap. 5. Advarsler kræver manuel vurdering."""
    warns = []
    vague = ("ofte", "nogle gange", "sommetider", "tit", "få minutter", "meget lidt", "normalt")
    for it in doc["items"]:
        texts = [("behavior", it["behavior"])] + [(q["id"], q["text"]) for q in it["questions"]]
        for label, t in texts:
            n = len(t.split())
            if n > 20 and label != "behavior":
                warns.append(f"{it['scenarioId']}/{label}: {n} ord (>20)")
            if label == "behavior" and n > 22:
                warns.append(f"{it['scenarioId']}: beskrivelse har {n} ord")
            if any(v in t.lower() for v in vague):
                warns.append(f"{it['scenarioId']}/{label}: vagt ord")
            if any(w in t.lower() for w in ("autis", "adhd", "diagnos", "sprogforstyr", "handicap")):
                warns.append(f"{it['scenarioId']}/{label}: diagnoseord")
    # balance af retning
    from collections import Counter
    rev = Counter((q["perspective"], i["scenarioId"][-1]) for i in doc["items"] for q in i["questions"] if q["reverseScored"])
    per = Counter(q["perspective"] for i in doc["items"] for q in i["questions"] if q["reverseScored"])
    print("Negativt formulerede pr. perspektiv:", dict(per))
    print("... pr. (perspektiv, adfærdstype):", dict(sorted(rev.items())))
    return warns


out = pathlib.Path(__file__).resolve().parent.parent / "data" / "sample_almenramme_survey.json"
out.write_text(json.dumps(survey, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Skrev {out} ({len(survey['items'])} items, {sum(len(i['questions']) for i in survey['items'])} spørgsmål)")
for w in lint(survey):
    print("LINT:", w)
