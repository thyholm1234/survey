# Analyseprotokol (version 1.0.0)

Alle regler er versionerede og gemmes i hver analysekørsel/eksport (`protocol`-objektet) sammen
med filtre, parametre, softwareversioner og SHA-256 af datagrundlaget (`dataSha256`). En CSV-eksport
med samme filtre giver samme hash som analysekørslen, hvilket dokumenterer reproducerbarhed.

## Population
- Standard: fuldførte besvarelser (`status=completed`) for valgt surveyversion og de afdelinger,
  brugeren har adgang til. Ufuldstændige kan inkluderes eksplicit (`includeIncomplete`).
- Ingen automatisk eksklusion. Hurtige respondenter og straightlining flagges kun.

## Scoring (`scoring/1.0.0`)
- Itemscore = rå værdi 1–6; reverse: `max + min − rå`.
- `CANNOT_ASSESS`, `NOT_ANSWERED` og `NOT_REACHED` er missing – aldrig midtpunkt eller 0.
- Subskalascore = middel af gyldige items, hvis andel gyldige ≥ 0,80 (konfigurerbar, rapporteres).
- Domænescore pr. subskala = middel af gyldige items, hvis andel ≥ 0,75 (dvs. 3 af 4 items).
- Ingen totalscore.
- Deskriptiv statistik: N, gyldige, missing %, middel, SD, median, IQR, 95 % t-baseret CI.
- Svartid: server-målt fra første visning til første svar; øvre winsorisering (99. percentil) kun i analyse.

## Reliabilitet
- Pr. subskala og pr. subskala × domæne (kun ≥ 3 items).
- Parvis-komplet kovariansmatrix (min. 10 observationer pr. itempar). `nComplete` rapporteres.
- Cronbachs alfa; 95 % percentil-bootstrap-CI (standard 1000 resamples, seed 20240601).
- Korrigeret item-total-korrelation, alfa-hvis-slettet, gennemsnitlig inter-item-korrelation.
- McDonalds omega total fra én-faktor principal axis factoring på Pearson-korrelationer.
  (Polychoriske korrelationer, EFA/CFA med WLSMV og måleinvarians er fase 2.)
- Heuristiske flag: item-total < .20; inter-item uden for .15–.50; alfa > .95. Alfa ≠ endimensionalitet.

## Gruppeforskelle (skole vs dagtilbud)
- Udfald: respondentens subskalascore.
- Primær model: lineær mixed model (statsmodels MixedLM, REML)
  `score ~ unit_type * subscale + kovariater + (1 | afdeling)`; desuden pr. subskala
  `score ~ unit_type + kovariater + (1 | afdeling)`. Kovariater (fx faggruppe, anciennitet) bruges kun,
  hvis > 80 % har svaret. Advarsel ved < 10 afdelinger. Respondent-random-effect (krydset) er fase 2.
- Supplerende: klassisk ANOVA (η², ω²), Welch-ANOVA, Kruskal-Wallis (ε²).
- Antagelser: Levene (Brown-Forsythe, median), Shapiro-Wilk og skævhed på residualer;
  uafhængighed er brudt ved afdelingsklynger – derfor er mixed model primær.
- Valg: Levene p < .05 → Welch + Games-Howell; ellers ANOVA + Tukey HSD. |skævhed| > 1 → anbefaling om
  Kruskal-Wallis/ordinal model.
- Effektstørrelse: Hedges g med 95 % CI (retning angives eksplicit).
- Grupper med n < max(k, 10) sammenlignes ikke.

## Teamniveau
- ICC(1) og ICC(2) fra envejs-ANOVA med k₀-justering for ulige gruppestørrelser.
- rwg(j) pr. afdeling med uniform nulfordeling (σ²ₑᵤ = (A²−1)/12). Median rwg(j) ≥ .70 → afdelingsmiddel
  kan fortolkes som fælles niveau; ellers vises det som "individuelle svar samlet".

## Datascreening (`screening/1.0.0`)
- Hurtig respondent: respondentens median-svartid < ⅓ af stikprøvens median.
- Straightlining: alle besvarede items i en blok har samme værdi (≥ 10 svar).
- Kun til følsomhedsanalyse – ingen sletning.

## Celleundertrykkelse (`suppression/1.0.0`)
1. Primær: celler med n < k (tenantens minimumscellestørrelse, min. 10) vises ikke.
2. Sekundær: i afdelingssammenligningen undertrykkes yderligere de mindste synlige afdelinger, indtil
   de undertrykte tilsammen har n ≥ k (forhindrer differencing mod totalen).
3. Komplementregel: ved aktive valgfrie filtre undertrykkes visningen, hvis 0 < N(uden filtre) − N(med
   filtre) < k.
4. Svarfordelinger vises kun for items med n ≥ k.

## Fortolkningsforbehold
Ingen individuelle medarbejderprofiler, ranglister, normering, kliniske cutoffs eller kausal
fortolkning. Afdelinger vises alfabetisk.
