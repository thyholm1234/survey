// Brugerfladetekster. Tilføj et nyt sprog ved at tilføje et objekt og sætte <html lang>.
const STRINGS = {
  da: {
    appTitle: 'Spørgeskema',
    codeLabel: 'Adgangskode',
    codeHint: 'Koden står i invitationen, fx ABCD-EFGH-JKMN. Store/små bogstaver og bindestreger er ligegyldige.',
    codeSubmit: 'Fortsæt',
    codeRequired: 'Indtast den adgangskode, du har fået udleveret.',
    resumeLink: 'Har du en genoptagelseskode?',
    resumeLabel: 'Genoptagelseskode',
    resumeSubmit: 'Genoptag besvarelse',
    infoHeading: 'Før du går i gang',
    purpose: 'Formål', voluntary: 'Frivillighed', dataController: 'Dataansvarlig',
    retention: 'Opbevaring', contact: 'Kontakt', pseudonymity: 'Dine oplysninger',
    estimated: (q, m) => `${q} spørgsmål · ca. ${m} minutter`,
    backgroundHeading: 'Baggrundsoplysninger (frivillige)',
    preferNot: 'Ønsker ikke at svare',
    consent: 'Jeg har læst informationen og vil gerne deltage',
    consentRequired: 'Du skal bekræfte, at du vil deltage, før du kan starte.',
    start: 'Start besvarelsen',
    resumeKeyHeading: 'Din genoptagelseskode',
    resumeKeyText: 'Skriv koden ned, hvis du vil kunne fortsætte senere fra en anden browser. Den vises kun nu.',
    copy: 'Kopiér kode', copied: 'Kopieret',
    continue: 'Fortsæt til spørgsmålene',
    behavior: 'Situation',
    cannotAssess: 'Kan ikke vurdere',
    prev: 'Tilbage', next: 'Næste', finish: 'Gå til afslutning',
    blockProgress: (b, n) => `Del ${b} af ${n}`,
    totalProgress: 'Samlet fremdrift',
    saved: 'Gemt', saving: 'Gemmer…', saveFailed: 'Kunne ikke gemme – prøver igen…',
    unansweredMark: 'Ikke besvaret – det er i orden at springe over.',
    reviewHeading: 'Klar til at afslutte?',
    reviewText: (n) => n === 0 ? 'Du har besvaret alle spørgsmål.' : `Du har ${n} ubesvarede spørgsmål. Du kan gå tilbage og besvare dem eller afslutte nu.`,
    goFirstUnanswered: 'Gå til første ubesvarede',
    complete: 'Afslut og indsend',
    doneHeading: 'Tak for din besvarelse',
    doneText: 'Dine svar er gemt. Resultaterne bruges kun samlet for grupper og vises aldrig for den enkelte.',
    sessionExpired: 'Din session er udløbet. Brug din genoptagelseskode for at fortsætte.',
    genericError: 'Der opstod en fejl. Prøv igen.',
  },
};
const lang = document.documentElement.lang in STRINGS ? document.documentElement.lang : 'da';
export const t = (key, ...args) => {
  const v = STRINGS[lang][key];
  return typeof v === 'function' ? v(...args) : (v ?? key);
};
