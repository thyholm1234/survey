# Sammenligning med Pearson Clinical (offentligt oplyst niveau)

**Sådan skal siden læses.** Pearsons interne kontroller kan ikke ses udefra. Sammenligningen bygger udelukkende på det, Pearson offentligt oplyser om
Q-global/Q-interactive og Clinical-platformene (sider og whitepapers, se kilder). Den dokumenterer *funktionelt* sammenfald og *organisatoriske* huller;
den kan ikke bevise, at løsningen er "på højde med Pearson". Pearsons styrke ligger især i det organisatoriske lag (ISO 27001-certificering, SOC, årlig ISMS-gennemgang).

| Pearson oplyser (offentligt) | Denne løsning | Gab |
|---|---|---|
| Informationssikkerhedspolitikker baseret på **ISO 27001**; Pearson Clinical **certificeret ISO 27001** i Europa (siden dec. 2021) | Kontroller afstemt til Annex A ([`security-controls.md`](security-controls.md)); **ikke certificeret** | ⬜ Organisatorisk: ISMS + audit ([`iso27001-roadmap.md`](iso27001-roadmap.md)) |
| Årlig lokal ISMS-gennemgang og risikovurdering under informationssikkerhedsansvarlig | Ingen formel proces | ⬜ |
| Security Operations Control overvåger infrastrukturen løbende; hændelser håndteres | Auditlog + healthchecks; ingen central overvågning/SOC | ⬜ monitorering/alarmer |
| **HTTPS/TLS** i transit | TLS i reverse proxy, HSTS, `upgrade-insecure-requests` | 🟡 verificér konfiguration i drift |
| **AES-256** i hvile | MariaDB-diskkryptering (AES) + GPG AES-256-backups | ✅ (nøglestyring 🟡) |
| **Tofaktor**, stærke adgangskoder, **automatisk logout** ved inaktivitet | TOTP obligatorisk, ≥ 14 tegn, Argon2id, 30 min inaktivitet / 8 t maks. | ✅ |
| **Indsamler ikke egentlige navne eller CPR** | Samme: ingen navn/e-mail/CPR/fritekst | ✅ |
| Kunden kan **eksportere og slette** data | Admin-eksport; tenant-sletning; respondentens egen eksport/sletning | ✅ |
| Databehandler for kundens GDPR-formål; underdatabehandlere bundet af aftaler | DPA-skabelon + underdatabehandler-liste | 🟡 aftaler skal underskrives |
| Hosting i EU (Bahnhof Stockholm, MongoDB Atlas Dublin) – tredjelandsoverførsler på adequacy/SCC-grundlag | Kun EU/EØS; ingen tredjepartsressourcer | ✅/🟡 vælg EU-host |
| AWS' SOC 2-rapport (underleverandør) på forespørgsel | Afhænger af valgt hostingudbyder | 🟡 indhent leverandørs ISO 27001/SOC 2 |
| Backups sikrer døgnet-rundt-tilgængelighed | Krypterede backups; ingen HA | 🟡 |
| Dedikeret Data Privacy Officer | `DPO_CONTACT`-felt | 🟡 udpeg |

**Beyond Pearson (hvor løsningen er stærkere end det offentligt oplyste):** k-anonymitet i alle resultater, hash-kædet manipulationssikret auditlog, registrerede-holdt nøgle til rettigheder uden identifikation,
streng CSP/Trusted Types uden tredjepartsscripts, uforanderlige publicerede instrumentversioner.

**Konklusion.** Det tekniske sikkerhedsniveau for denne type data er på højde med det, Pearson offentligt beskriver, og på flere punkter strengere. Det, der adskiller en Pearson-leverance, er et certificeret ledelsessystem,
ekstern verificering (revision, penetrationstest) og døgndrift/overvågning. De tre er mulige at opnå, men kræver organisation og tid, ikke mere kode.

## Kilder
- Pearson Clinical, *Digital Platforms Operations – Platform security & privacy*: https://www.pearsonclinical.nl/platform_security_privacy
- Pearson Clinical, *Whitepaper Q-global and Q-interactive* (UK/SE): https://www.pearsonclinical.co.uk/content/dam/school/global/clinical/uk-clinical/assets/q-interactive/Pearson-Whitepaper-Q-global-and-Q-interactive-UK.pdf
- Pearson, *Cyber Resilience Pledge*: https://www.pearson.com/privacy-center/cyber-resilience-pledge.html
