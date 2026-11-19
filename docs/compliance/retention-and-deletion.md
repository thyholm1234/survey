# Opbevaring og sletning

| Datatype | Placering | Periode | Mekanisme | Status |
|---|---|---|---|---|
| Rå besvarelser, svar, hændelser | `qa_data` | Pr. tenant (`retentionMonths`, standard 24) fra start | Automatisk, hver time (`services/retention.py`); respondent kan slette før (art. 17) | ✅ |
| Personlig kode (genoptagelse/rettigheder) | `qa_identity.resume_keys` | Til opbevaringsperiodens udløb; genoptagelse af uafsluttet i `RESUME_KEY_TTL_DAYS` (standard 14) | Automatisk | ✅ |
| Respondent-/adminsessioner, kodebilletter | `qa_identity` | Minutter til timer (inaktivitet/absolut maks.) | Automatisk | ✅ |
| Rate-limit-poster (IP som dagligt roterende HMAC) | `qa_identity.rate_limits` | Udløber efter 15 min; slettes ved næste timevise oprydning | Automatisk | ✅ |
| Analyseresultater | `qa_analysis` | Slettes med tenant | Manuelt/tenant-sletning | 🟡 ingen automatisk frist |
| Auditlog (ingen svar; aktør-id, handling, tid) | `qa_audit` | **Ingen sletteregel i dag** | – | ⬜ Beslut frist (anbefaling: 24–36 mdr.) og byg *arkivering med forankret kædehash*, så sletning ikke bryder hash-kæden |
| Krypterede backups | Ekstern lagring | `BACKUP_KEEP_DAYS` (standard 35) | `scripts/backup.sh` sletter ældre | ✅ — husk at slettede data forbliver i backups til de udløber; oplys det ved sletteanmodninger |
| Admin-konti | `qa_identity.users` | Til brugeren deaktiveres/tenant slettes | Manuelt | 🟡 |
| Ved kundeophør | Alle | Straks efter udlevering | Systemadmin sletter tenant (bekræftet med navn); logbog bevares | ✅ |
