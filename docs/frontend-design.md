# Frontend-design

Hele frontenden (respondent og admin) følger et "modern SaaS"-designsystem: hvid base, serif-overskrifter
(Playfair Display), sans-serif til alt andet (Inter), ét grønt accent og varm gul til data.
Alle værdier er tokens øverst i `frontend/css/app.css`.

## Tilpasninger, der er bevidste afvigelser fra et marketing-design

| Krav i appen | Konsekvens for designet |
|---|---|
| CSP `script/style/font-src 'self'`, ingen tredjepart | Skrifttyper er selvhostet (`frontend/fonts/`, OFL). Ikoner er Lucide indlejret som data i `js/icons.js` (genereres af `scripts/build_icons.py`) – ingen CDN. Respondenters IP sendes aldrig til Google. |
| Trusted Types, ingen `innerHTML` | Ikoner bygges med `createElementNS`. |
| WCAG 2.2 AA (axe i `tests/e2e/a11y.mjs`) | Knapper bruger `#3d7a1f` (5,2:1 på hvid). Brandgrønnen `#5ea832` giver kun 2,9:1 og bruges derfor kun til dekoration. Muted tekst er `#6f6f6f`, ikke `#999`. |
| Diagrammer skal kunne aflæses uden farve | De to serier skelnes også på form (cirkel = dagtilbud, firkant = skole). Heatmap-celler har værdien skrevet i cellen. |
| Bevægelsesfølsomhed | Al animation er slået fra under `prefers-reduced-motion`. Indgangsanimationen bruger kun `transform`, aldrig `opacity`, så kontrast aldrig måles midt i en overgang. |
| Mørk tilstand | Fuldt tema via `prefers-color-scheme`. |

## Hvad der bevidst ikke er med

Sektionerne hero-flydekort, logo-marquee, priser, udtalelser og tællende nøgletal er ikke brugt: de ville kræve
opdigtede data eller logoer og passer ikke til et pseudonymt spørgeskema. Hero-mønstret (badge, serif-overskrift,
krydsskravering, stiplede linjer, glød) bruges på respondentens startside og admin-login. FAQ-akkordeonen på
startsiden er en native `<details>`.

## Genopbyg ikoner

```bash
python3 scripts/build_icons.py   # henter Lucide ved byggetid og skriver frontend/js/icons.js
```
