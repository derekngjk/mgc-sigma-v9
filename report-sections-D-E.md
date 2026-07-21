# Sections D & E — drafted for the MGC Mid-Term Review Written Pitch

> Copy-paste source, ≤500 words for D + E combined (count excludes this note and the headings). British spelling. "Kinly" is the product name; "Sigma Tech v9" remains the team/project label. Survey references stay consistent with Section B.

---

## D. Explain how your product or solution works

Kinly is an AI-powered patient communication assistant embedded in the clinician's EHR workflow. The pipeline runs live on Synapxe's HealthX Innovation Sandbox over FHIR R4B — a working system, not a concept.

1. **Ingest.** Kinly pulls Patient, Condition, CarePlan and Observation resources from the EHR and diffs active conditions against the last approved summary (new / ongoing / resolved), so every report tells the family what changed.

2. **Translate.** Generation is governed by a prompt system authored by our team's medical students, encoding clinical judgement as hard rules: a 12-year-old reading level; no term left unexplained — e.g. "diabetic ketoacidosis (when a lack of insulin makes the blood dangerously acidic)"; one everyday analogy; do/don't/red-flag lists; doses and lab values excluded. Four audience-specific prompts mean the patient, spouse, adult child and caregiver each receive a differently written document, not a re-toned copy.

3. **Verify.** Optionally, a second independent LLM audits the draft against the source record alone, flagging unsupported claims (hallucinations), omissions and risky simplifications as an advisory verdict to the clinician.

4. **Approve.** Nothing reaches a family without clinician sign-off. Record and editable draft sit side by side; the delivered text is the clinician's edited text, verbatim. The workflow is two actions — Generate, Approve — as published evidence shows AI-draft review can double task time.

5. **Deliver.** Approved summaries appear in a role-scoped portal: each care-circle member registers under their role and sees only summaries written for them, with per-user read tracking. Accounts link to the patient via a peppered HMAC of name + NRIC — the raw NRIC is never stored; passwords are PBKDF2-hashed — and production replaces this PoC login with Singpass/Myinfo verified identity. Summaries are readable in English, Chinese, Malay and Tamil via an MOH-aligned clinical glossary, listenable through sentence-synchronised text-to-speech, printable, and optionally illustrated with a dose-scrubbed anatomy infographic for low-literacy readers.

Every design choice traces to our pilot survey (Section B): every caregiver wanted written summaries they could revisit, and doctors' top frustration was repeating explanations — Kinly lets a clinician approve once and serve the whole care circle. Existing tools are clinician-facing (RUSSELL-GPT), passive (HealthHub) or generic (pamphlets); to our knowledge, Kinly is the only product combining patient-specific AI translation, per-role family delivery and a hard clinician approval gate.

## E. Provide an analysis and evaluation of your product (SWOT)

### Strengths

Working end-to-end system on national sandbox rails; medically-authored prompts competitors cannot trivially replicate; dual-layer safety (independent AI audit plus mandatory human approval); role-scoped, four-language, multi-modal delivery unmatched by existing tools.

### Weaknesses

Validated on synthetic data only — clinical validation and NEHR-grade integration remain; summary quality bounded by record completeness; Malay/Tamil clinical translations not yet formally validated; per-summary inference cost and latency at ward scale.

### Opportunities

Synapxe alignment gives a natural NEHR/HealthHub integration path; Singpass onboarding of the care circle; value-based contracts tied to staff time savings and patient satisfaction scores; the multilingual, multi-role architecture generalises regionally.

### Threats

Evolving AI-SaMD regulation (AIHGle) and PDPA/Cybersecurity Act compliance; incumbents pivoting to patient-facing communication; sector-wide trust shocks from AI clinical errors elsewhere; LLM provider dependency, mitigated by our three-provider abstraction.

---

## Appendix — PoC evidence (screenshots)

> Not part of the ≤500-word D+E body. All captures are from the running PoC (19 July 2026) on synthetic data, following §D's five steps end to end. Clinician-side figures use "Nurul Aisyah" (endocrine record fetched live from the HealthX sandbox); portal figures use "Tan Mei Ling" (mock oncology record). Captions are rendered inside each image.

### Ingest (§D step 1) — live from the national sandbox

![Figure 1 — live FHIR fetch with parsed active conditions](report-assets/clinician-fetch-live.jpg)

### Translate (§D step 2) — audience-specific documents, not re-toned copies

![Figure 2 — patient-audience summary in English](report-assets/portal-report-patient-en.jpg)

![Figure 3 — spouse-audience summary of the same record](report-assets/portal-report-spouse-en.jpg)

![Figure 4 — do / avoid / red-flag lists](report-assets/portal-report-action-lists.jpg)

### Verify (§D step 3) — independent AI audit of the draft

![Figure 5 — draft beside the record with the review toggled on](report-assets/clinician-draft-review.jpg)

![Figure 6 — the reviewer's three-category advisory verdict](report-assets/clinician-review-flags.jpg)

### Approve (§D step 4) — gated clinician workflow

![Figure 7 — clinician sign-in gate](report-assets/clinician-login-gate.jpg)

![Figure 8 — approval with care-circle delivery confirmation](report-assets/clinician-approved-delivered.jpg)

### Deliver (§D step 5) — role-scoped portal for the care circle

![Figure 9 — care-circle registration with name + NRIC linking](report-assets/portal-register-spouse.jpg)

![Figure 10 — patient dashboard](report-assets/portal-dashboard-patient.jpg)

![Figure 11 — spouse dashboard, same patient](report-assets/portal-dashboard-spouse.jpg)

![Figure 12 — Chinese translation](report-assets/portal-report-zh.jpg)

![Figure 13 — sentence-synchronised listening](report-assets/portal-report-listen.jpg)

![Figure 14 — dose-scrubbed visual aid](report-assets/portal-report-illustration.jpg)
