# Sections D & E — drafted for the MGC Mid-Term Review Written Pitch

> Copy-paste source. Written to match the register of the existing report. "Kinly" is used as the product name throughout (the cover-page "Sigma Tech v9" remains the team/project label). Survey figures are quoted exactly as they appear in Section B so the report stays internally consistent.

---

## D. Explain how your product or solution works

Kinly is an AI-powered patient communication assistant that lives inside the clinician's existing Electronic Health Record (EHR) workflow. It reads the patient's live clinical record, drafts a plain-language summary tailored to each member of the patient's care circle, passes that draft through two layers of safety review — an independent AI cross-check and a mandatory clinician sign-off — and then delivers the approved summary to the patient and family through a secure portal, in their own role and their own language. The entire loop is not a concept: it runs end-to-end today against Synapxe's HealthX Innovation Sandbox over the FHIR R4B standard, the same interoperability layer used by Singapore's public healthcare IT infrastructure.

The workflow has five steps:

**1. Kinly reads the record where it already lives.** Kinly pulls the patient's demographics, active conditions, care plans, and observations directly from the EHR via FHIR — no re-typing, no copy-pasting into a chatbot. Critically, every new summary is automatically compared against the last one the clinician approved: conditions are classified as *new*, *ongoing*, or *resolved*, and the summary explicitly walks the family through what has changed since their last update. This directly addresses what our pilot survey (Section B) identified as the core anxiety driver — 80% of caregivers and two-thirds of patients reported anxiety from a lack of updates. Families should never have to wonder whether something changed; Kinly tells them.

**2. It translates the record using prompts written by medical students, not engineers.** This is where Kinly departs most sharply from generic "summarise this with AI" tools. The instructions that govern every summary were authored and iterated by the medical students on our team — people who have stood in ward rounds and know both what doctors need conveyed and what actually confuses families. The prompt system encodes that clinical judgement as hard rules: every summary is written at a level a 12-year-old could follow; no medical term is ever left unexplained (each one is immediately restated in plain words — e.g. "diabetic ketoacidosis (when a lack of insulin makes the blood dangerously acidic)"); exactly one everyday analogy anchors the main problem; every summary ends in concrete do's, don'ts, and when-to-seek-help lists; the tone is honest but reassuring, never frightening; and exact medication doses, lab values, and clinical codes are deliberately excluded, because they invite dangerous self-interpretation.

Just as importantly, Kinly does not write one summary and re-tone it. It writes a **different document for each audience**. A patient receives an empowering second-person summary ("you", "your"). A spouse receives one focused on providing support at home and the difficulty of caring for a partner. An adult child receives one that acknowledges the role reversal of caring for a parent. A professional or family caregiver receives the most clinical version — daily monitoring points and red-flag signs, prioritising actionable information over emotional framing. Clinicians choose the audience and one of three lengths (roughly 100, 250, or 450 words) with two clicks.

**3. A second, independent AI checks the first — before any human reads it.** At the clinician's option, Kinly runs the draft past a second large language model whose only job is scepticism: it compares the draft against the source clinical facts and flags unsupported claims (possible hallucinations), clinically important omissions, and simplifications risky enough to mislead. The verdict is presented to the clinician as an advisory panel — explicitly labelled as *not* an approval — so it sharpens human review rather than replacing it. The reviewer can even run on a different AI provider than the writer, so the two models do not share blind spots.

**4. Nothing reaches a family without a clinician's signature.** The clinician sees the raw clinical record and the AI draft side by side, edits the draft directly in place, and approves it — and the text that gets delivered is *the clinician's edited text*, verbatim. This human-in-the-loop gate is a hard architectural rule, not a policy promise: there is no code path from the AI to a family that does not pass through approval. We also designed the review screen around published evidence — studies of AI-drafted patient messaging (JAMIA / npj Digital Medicine) found that reviewing AI drafts can more than double a task's time cost if the interface is clumsy, so Kinly's entire clinician workflow is two actions: Generate, then Approve. Our survey told us why this gate matters to families too: 60% of caregivers said inconsistent updates eroded their trust in the care team. Trust survives only if every message is genuinely the care team's own.

**5. The approved summary reaches the whole care circle — each person in their own role, language, and format.** On approval, the summary is delivered automatically to the patient's secure portal. Family members register themselves, choosing their role — patient, spouse/partner, adult child, or caregiver — and each account sees only the summaries written for that role, with per-person unread tracking. (In this PoC, family members link to the patient using the patient's full name and NRIC; in the production product this login is replaced by **Singpass**, Singapore's national digital identity, giving verified identity assurance and Myinfo-backed patient linking with no separate passwords to manage.) Every summary can be read in any of Singapore's four official languages — English, Chinese, Malay, and Tamil — translated with a clinician-curated glossary sourced from HealthHub/MOH terminology. For elderly users and low-literacy readers, each summary can be *listened to*, with the text highlighting sentence by sentence as the audio plays, and the font scales up to large-print sizes. Kinly can also attach a generated patient-education illustration — a calm, labelled anatomy diagram with colour-coded "watch for / do / don't" panels, mechanically scrubbed of doses and alarming language. For families who are offline, the clinician can print a formatted handout of the same approved summary in one click.

**Privacy is built into the architecture, not bolted on.** Kinly never stores the raw NRIC — only a peppered cryptographic hash (an HMAC keyed with a server-side secret) used to match a family's registration to the right patient. Passwords are hashed with PBKDF2 (240,000 iterations, per-user salts). Clinician and family logins live in entirely separate authentication systems, so a portal credential can never touch clinician functions. Because identity is already keyed to a derived hash rather than raw credentials, swapping the PoC login for Singpass changes the front door, not the data model. And the PoC operates exclusively on synthetic patient data — no real PHI has ever entered the system.

### Why Kinly is different

Every major design decision in Kinly traces to something a doctor, patient, or caregiver told us in our pilot survey (Section B) — the product is the survey's findings, engineered:

- **Every caregiver we surveyed said updates were mostly verbal, and all of them wished for written summaries they could refer back to later.** Kinly's core output is exactly that: a permanent, re-readable, re-listenable written summary.
- **Doctors' most-cited frustration was repeating the same explanation to multiple family members, with 94% citing heavy workload from family updates.** Kinly's role-scoped care-circle delivery means the clinician approves once and every family member receives their own appropriately-framed version — the repetition is eliminated by design, not by asking doctors to type faster.
- **80% of caregivers reported anxiety from a lack of updates.** Kinly's change-tracking means every report opens with what is new and what has resolved since the family last heard from the team.
- **60% of caregivers said inconsistent updates damaged trust.** Kinly's mandatory clinician sign-off guarantees every message is consistent with — and owned by — the care team.

Against the existing landscape (Section C), this positioning is unique. Clinician-facing AI tools such as RUSSELL-GPT streamline communication *between professionals* and still speak in jargon; Kinly is built exclusively for the patient-and-family side of the conversation. Portals such as HealthHub are passive repositories that make families do the searching and interpreting; Kinly proactively delivers an explanation written for a specific person's role and reading level. Pamphlets are generic; every Kinly summary is generated from *this* patient's record, *this* admission, *this* change in condition. To our knowledge, no existing product combines patient-specific AI translation, per-role family delivery, and a hard clinician approval gate in one workflow — and none of them writes its prompts the way we do: with medical students encoding what doctors actually want families to hear.

---

## E. Provide an analysis and evaluation of your product

**SWOT Analysis**

**Strengths**

- **A working product, not a mock-up.** Kinly runs end-to-end today — live FHIR integration on Synapxe's HealthX Innovation Sandbox, AI generation, dual-layer review, and portal delivery — which materially de-risks the build for a healthcare buyer.
- **Clinically-authored intelligence.** Our prompts, glossaries, and safety rules were written by the medical students on the team and encode clinical communication judgement (jargon rules, tone, what to omit) that a generic AI wrapper cannot replicate.
- **Dual-layer safety as architecture.** An independent second-model cross-check plus a mandatory human-in-the-loop approval gate means no AI output can ever reach a family unreviewed — the property hospitals will demand first.
- **Role-scoped care-circle delivery.** Writing a genuinely different document for the patient, spouse, adult child, and caregiver — delivered to each person's own account — is, to our knowledge, unmatched by any competitor and directly answers the surveyed doctors' top frustration.
- **Built for Singapore's population.** All four official languages with MOH/HealthHub-aligned terminology, read-aloud audio with follow-along highlighting, large-print scaling, and visual aids extend the product to elderly and low-literacy users — the very groups Section B shows are most affected.
- **Privacy by design.** No raw NRIC is ever stored, credentials are strongly hashed, clinician and family authentication are fully separated, and the identity model is already Singpass-ready.
- **Survey-validated demand.** The product's core outputs map one-to-one onto what our pilot survey of doctors, patients, and caregivers asked for (Section B).

**Weaknesses**

- The PoC has been validated only on synthetic data; production deployment requires integration with live hospital systems (NEHR-grade), formal clinical validation of summary accuracy, and prospective evaluation of outcomes.
- Summary quality is bounded by the structure and completeness of the underlying record — sparse or poorly-coded records yield thinner summaries.
- Multilingual clinical accuracy (particularly Malay and Tamil) requires ongoing review by qualified bilingual clinicians; we have a curated glossary but no formal translation-validation study yet.
- Each summary, review, translation, and audio render incurs per-call AI inference cost and latency, which must be engineered down at ward scale.
- As with any hospital software, procurement and information-security accreditation cycles are long, raising customer acquisition cost.

**Opportunities**

- **National infrastructure alignment.** Building on Synapxe's FHIR rails positions Kinly for a natural integration path with NEHR and HealthHub rather than competing against them — and **Singpass integration** gives verified-identity onboarding of the care circle on rails the whole population already uses.
- **Departmental and cluster expansion** along the roadmap in Section F: from one high-dependency department to Geriatrics, Rehabilitation, Oncology, and ultimately all three public healthcare clusters.
- **Modality expansion.** The audience-and-language architecture generalises: spoken dialects for elderly patients, proactive notifications, and caregiver-specific education content are additive, not rebuilds.
- **Value-based revenue.** Future contracts can be tied to measurable outcomes hospitals already track — documented staff time savings and patient satisfaction scores — aligning our incentives with the buyer's.
- **Regional generalisation.** The multilingual, multi-role design transfers naturally to other multilingual healthcare systems in Southeast Asia.

**Threats**

- **Evolving AI regulation.** Kinly may be classified as AI Software as a Medical Device; HSA's AIHGle guidelines, the PDPA, and the Cybersecurity Act impose compliance obligations that will evolve faster than typical software requirements.
- **Incumbent pivot.** Established players (e.g. RUSSELL-GPT, EHR vendors adding patient-messaging AI) could extend into patient-facing communication; our defence is the depth of the family-side workflow — role scoping, languages, accessibility, and the approval gate — which is costly to retrofit.
- **Sector-wide trust shocks.** A high-profile AI clinical error anywhere in the industry could harden hospital risk appetite against all LLM products, regardless of our safeguards.
- **Model-provider dependency.** Pricing or policy changes by AI providers affect unit economics — partially mitigated because Kinly is already provider-agnostic, running interchangeably on three major AI vendors.
