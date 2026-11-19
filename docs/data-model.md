# Datamodel

Fire databaser. Pile mellem databaser er fremmednøgler; `qa_data` har bevidst **ingen** reference til
`access_codes` eller brugere (kun `imported_by`/`published_by` som ikke-FK id'er), så analysedata kan
udleveres uden identitets-/adgangsdata.

```mermaid
erDiagram
  %% qa_data
  tenants ||--o{ organization_units : har
  organization_units ||--o{ organization_units : "parent"
  tenants ||--o{ surveys : ejer
  surveys ||--o{ survey_versions : versioner
  survey_versions ||--|| response_scales : skala
  survey_versions ||--o{ subscales : perspektiver
  survey_versions ||--o{ domains : domæner
  survey_versions ||--o{ scenarios : adfærdsbeskrivelser
  domains ||--o{ scenarios : ""
  scenarios ||--o{ questions : ""
  subscales ||--o{ questions : ""
  survey_versions ||--o{ responses : ""
  organization_units ||--o{ responses : ""
  responses ||--o{ answers : "cascade"
  questions ||--o{ answers : ""
  responses ||--o{ presentation_events : "cascade"

  %% qa_identity
  users ||--o{ user_scopes : ""
  roles ||--o{ user_scopes : ""
  users ||--o{ admin_sessions : ""
  tenants ||--o{ access_codes : ""
  organization_units ||--o{ access_codes : ""
  survey_versions ||--o{ access_codes : ""
  access_codes ||--o{ code_tickets : ""
  access_codes ||--o{ response_sessions : ""
  responses ||--o{ response_sessions : "cascade"
  responses ||--o| response_links : "cascade"

  responses {
    char32 id PK "pseudonymt responseId"
    char32 unit_id FK
    string unit_type "snapshot"
    json background "kun godkendte kategorier"
    json group_tags
    bigint seed
    json block_order
    json presentation_order "faktisk rækkefølge"
    json randomization_meta
    string browser_class
    string screen_class
    datetime started_at
    datetime completed_at
    bool is_synthetic
  }
  answers {
    smallint value "NULL ved missing"
    string missing_code "CANNOT_ASSESS"
    smallint global_position
    smallint block_index
    smallint block_position
    datetime first_shown_at
    datetime answered_at
    int rt_ms
    smallint change_count
    bool changed_after_back
    int last_seq "idempotens"
  }
  access_codes {
    char32 id PK "codeId"
    char64 lookup_hmac UK
    string code_hash "Argon2id"
    datetime valid_from
    datetime valid_to
    string status
  }
```

Øvrige tabeller: `qa_identity.rate_limits` (pseudonymiseret bucket, udløb), `qa_analysis.analysis_runs`
(filtre, parametre, tilladte afdelinger, resultat, softwareversioner, datahash),
`qa_audit.audit_events` (hash-kæde: `prev_hash`, `hash`).

## Personlige adgangskoder

Alle adgangskoder er personlige: højst én besvarelse ad gangen pr. kode. Koblingen kode → besvarelse
findes kun i `qa_identity.response_links` (ikke i analysedata) og udløber med opbevaringsperioden.
Deltageren logger ind igen med koden for at fortsætte en påbegyndt besvarelse eller for at trække en
besvarelse tilbage (den slettes helt, auditeres som `respondent.withdrawn`) og derefter svare forfra.
Koden virker også på siden om rettigheder (indsigt/sletning), også efter at koden er udløbet. Koderne
udleveres som PDF (`POST /api/admin/access-codes/personal-pdf`): én forside til den ansvarlige pr.
afdeling og én side pr. kode med vejledning og QR-kode (`/#kode=…`; fragmentet sendes ikke til serveren).
Klartekst gemmes ikke.

## Missing-koder i analysedata
| Kode | Betydning |
|---|---|
| `CANNOT_ASSESS` | Respondenten valgte "Kan ikke vurdere" |
| `NOT_ANSWERED` | Vist (`first_shown_at` sat), men ikke besvaret |
| `NOT_REACHED` | Aldrig vist (besvarelsen stoppede før) |
