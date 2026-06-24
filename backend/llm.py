import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_MODEL = "claude-opus-4-7"
OPENAI_MODEL = "gpt-4o"
GEMINI_MODEL = "gemini-3.5-flash"

# Singapore's four official languages available for family viewer translation.
_SUPPORTED_LANGS: dict[str, str] = {
    "zh": "Simplified Chinese (简体中文)",
    "ms": "Malay (Bahasa Melayu)",
    "ta": "Tamil (தமிழ்)",
}

# Clinical term glossary injected into the translation prompt for consistency.
#
# Sources:
#   [1] HealthHub A-Z Medications Glossary (healthhub.sg — MOH Singapore patient portal)
#       https://www.healthhub.sg/medication-devices-and-treatment/medications
#   [2] Cambridge Dictionary bilingual entries (dictionary.cambridge.org)
#       EN→ZH-Hans: /dictionary/english-chinese-simplified/
#       EN→MS:      /dictionary/english-malaysian/
#       EN→TA:      /dictionary/english-tamil/
#   [3] Official institution names — MOH Singapore, NCCS, SingHealth
#       https://www.nccs.com.sg  |  https://www.moh.gov.sg
_CLINICAL_GLOSSARY: dict[str, dict[str, str]] = {
    "zh": {
        # Common clinical nouns — sources [1][2]
        "cancer": "癌症",
        "tumour": "肿瘤",
        "tumor": "肿瘤",
        "chemotherapy": "化疗",
        "radiation therapy": "放射治疗",
        "radiotherapy": "放射治疗",
        "biopsy": "活检",
        "metastasis": "癌细胞转移",
        "surgery": "手术",
        "palliative care": "舒缓治疗",  # MOH/SingHealth Singapore usage [1]
        # Drug brand names and institutions — source [3]
        "Herceptin": "赫赛汀",
        "National Cancer Centre Singapore": "新加坡国家癌症中心",
        "Singapore General Hospital": "新加坡中央医院",
    },
    "ms": {
        # Common clinical nouns — sources [1][2]
        "cancer": "kanser",
        "tumour": "tumor",
        "tumor": "tumor",
        "chemotherapy": "kemoterapi",
        "radiation therapy": "terapi sinaran",  # "sinaran" = ray/beam in Malay [2]
        "radiotherapy": "radioterapi",
        "biopsy": "biopsi",
        "metastasis": "metastasis",
        "surgery": "pembedahan",
        "palliative care": "penjagaan paliatif",
        # Drug brand names and institutions — source [3]
        "Herceptin": "Herceptin",
        "National Cancer Centre Singapore": "Pusat Kanser Negara Singapura",
        "Singapore General Hospital": "Hospital Umum Singapura",
    },
    "ta": {
        # Common clinical nouns — sources [1][2]
        "cancer": "புற்றுநோய்",
        "tumour": "கட்டி",
        "tumor": "கட்டி",
        "chemotherapy": "கீமோதெரபி",
        "radiation therapy": "கதிர்வீச்சு சிகிச்சை",
        "radiotherapy": "கதிர்வீச்சு சிகிச்சை",
        "biopsy": "திசு பரிசோதனை",
        "metastasis": "புற்றுநோய் பரவல்",
        "surgery": "அறுவை சிகிச்சை",
        "palliative care": "தணிப்பு சிகிச்சை",
        # Drug brand names and institutions — source [3]
        "Herceptin": "ஹெர்செப்டின்",
        "National Cancer Centre Singapore": "சிங்கப்பூர் தேசிய புற்றுநோய் மையம்",
        "Singapore General Hospital": "சிங்கப்பூர் பொது மருத்துவமனை",
    },
}

VALID_AUDIENCES = {"patient", "spouse", "child", "caregiver"}

_SYSTEM_PROMPT_BASE = (
    "You are a medical communicator helping people understand complex clinical information. "
    "Translate the clinical data provided into clear, empathetic language. "
    "Use a relatable everyday analogy to explain the main condition. "
    "Avoid medical jargon. Use Markdown formatting: **bold** for key terms, "
    "## headings for sections, and - bullet points for lists where appropriate."
)

# Audience-specific tone and framing instructions.
_AUDIENCE_INSTRUCTIONS: dict[str, str] = {
    "patient": (
        "Write directly to the patient using 'you' and 'your'. "
        "Be empowering and reassuring — the patient is the focus of care. "
        "Explain what is happening in their body, what the care team is doing, "
        "and what they can expect. Use a warm, first-person tone throughout."
    ),
    "spouse": (
        "Write to the patient's spouse or partner using 'your partner' or 'your loved one'. "
        "Explain the patient's condition in the third person. "
        "Focus on how the spouse can provide emotional support, what to expect at home, "
        "practical caregiving tips, and when to contact the care team. "
        "Acknowledge the difficulty of supporting a loved one through this."
    ),
    "child": (
        "Write to the patient's adult child using 'your parent' or 'your mum / dad'. "
        "Explain the condition clearly without being overly clinical. "
        "Focus on how the adult child can support their parent, what changes to expect "
        "in daily life, and how to balance caregiving with their own wellbeing. "
        "Be emotionally sensitive — this is a difficult role reversal."
    ),
    "caregiver": (
        "Write to a professional or family caregiver in a clear, practical tone. "
        "Cover: what symptoms to monitor daily, red-flag signs that require urgent attention, "
        "medication or treatment schedule context, mobility or comfort considerations, "
        "and who to call for help. Prioritise actionable information over emotional framing."
    ),
}

# Length → word-count target and structural guidance injected into each prompt.
_LENGTH_INSTRUCTIONS: dict[str, str] = {
    "short": (
        "Length: 1-2 paragraphs, approximately 80-120 words. "
        "Cover only: (1) the main diagnosis in plain language, "
        "(2) the key treatment in one sentence. Omit all other detail."
    ),
    "medium": (
        "Length: 3-4 paragraphs, approximately 200-280 words. "
        "Cover: (1) the main diagnosis with a brief everyday analogy, "
        "(2) the treatment plan, (3) what the patient/family can expect next, "
        "(4) a short supportive closing."
    ),
    "long": (
        "Length: 5-6 paragraphs, approximately 380-480 words. "
        "Cover: (1) the main diagnosis with a relatable everyday analogy, "
        "(2) detailed treatment plan and why each step matters, "
        "(3) notable condition changes since the last report, "
        "(4) side effects or things to watch out for, "
        "(5) practical next steps or support resources, "
        "(6) an empathetic closing."
    ),
}


class LLMError(Exception): ...


class LLMConfigError(LLMError): ...


def generate_summary(
    raw_clinical_text: str,
    target_audience: str,
    condition_diff: dict | None = None,
    length: str = "medium",
) -> str:
    length_instruction = _LENGTH_INSTRUCTIONS.get(
        length, _LENGTH_INSTRUCTIONS["medium"]
    )

    diff_section = ""
    if condition_diff:
        added = condition_diff.get("added", [])
        removed = condition_diff.get("removed", [])
        ongoing = condition_diff.get("ongoing", [])
        parts: list[str] = []
        if ongoing:
            parts.append(f"Ongoing conditions: {', '.join(ongoing)}")
        if added:
            parts.append(f"New conditions since last report: {', '.join(added)}")
        if removed:
            parts.append(f"Resolved conditions since last report: {', '.join(removed)}")
        if parts:
            diff_section = "\n\nCondition summary:\n" + "\n".join(
                f"- {p}" for p in parts
            )
        if added or removed:
            diff_section += (
                "\n\nChanges since last report: please mention these changes clearly."
            )
    audience_instruction = _AUDIENCE_INSTRUCTIONS.get(
        target_audience, _AUDIENCE_INSTRUCTIONS["patient"]
    )
    prompt = (
        f"{_SYSTEM_PROMPT_BASE}\n\n"
        f"Audience: {audience_instruction}\n\n"
        f"{length_instruction}"
        f"{diff_section}\n\n"
        f"Clinical data (JSON):\n{raw_clinical_text}"
    )
    return _call_llm(prompt)


def translate_summary(text: str, lang: str) -> str:
    """Translate an approved English summary into a Singapore official language.

    Returns text unchanged for lang='en'.
    Raises LLMConfigError for an unsupported language code or misconfigured provider.
    Raises LLMError if the LLM call fails.
    """
    if lang == "en":
        return text
    if lang not in _SUPPORTED_LANGS:
        raise LLMConfigError(
            f"Unsupported language: {lang!r}. Supported non-English codes: {list(_SUPPORTED_LANGS)}"
        )
    lang_name = _SUPPORTED_LANGS[lang]
    glossary = _CLINICAL_GLOSSARY.get(lang, {})
    glossary_lines = "\n".join(f"  {en} → {target}" for en, target in glossary.items())
    prompt = (
        f"Translate the following patient health summary from English into {lang_name}.\n\n"
        "Rules:\n"
        "- Preserve the warm, empathetic tone exactly.\n"
        "- Keep the same paragraph and heading structure (separate paragraphs with a blank line).\n"
        "- Preserve all Markdown formatting markers exactly as they appear: **bold**, *italic*, ## headings, - list items.\n"
        "- Use the medical term translations listed below for consistency.\n"
        "- Return only the translated text. No explanations, no added commentary.\n\n"
        f"Medical term reference (use these translations):\n{glossary_lines}\n\n"
        f"Summary to translate:\n{text}"
    )
    # Tamil and Malay scripts are token-heavy (Tamil Unicode chars cost 2-4 tokens
    # each in most tokenizers), so translations need more headroom than summaries.
    return _call_llm(prompt, max_tokens=4096)


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise LLMConfigError("ANTHROPIC_API_KEY is not set")
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    elif LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise LLMConfigError("OPENAI_API_KEY is not set")
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    elif LLM_PROVIDER == "google":
        if not GEMINI_API_KEY:
            raise LLMConfigError("GEMINI_API_KEY is not set")
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    else:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. Use 'anthropic', 'openai', or 'google'."
        )
