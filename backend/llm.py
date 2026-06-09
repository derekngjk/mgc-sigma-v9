import os

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_MODEL = "claude-opus-4-7"
OPENAI_MODEL = "gpt-4o"

_SYSTEM_PROMPT = (
    "You are a medical translator helping patients and their families understand "
    "complex clinical information. Translate the clinical data provided into clear, "
    "empathetic language that a {target_audience} can understand. "
    "Use a relatable everyday analogy to explain the main condition. "
    "Write in a warm, supportive tone. Avoid medical jargon. "
    "Keep the response to 3-4 short paragraphs."
)


class LLMError(Exception): ...
class LLMConfigError(LLMError): ...


def generate_summary(
    raw_clinical_text: str,
    target_audience: str,
    condition_diff: dict | None = None,
) -> str:
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
            diff_section = "\n\nCondition summary:\n" + "\n".join(f"- {p}" for p in parts)
        if added or removed:
            diff_section += "\n\nChanges since last report: please mention these changes clearly."
    prompt = (
        f"{_SYSTEM_PROMPT.format(target_audience=target_audience)}"
        f"{diff_section}\n\n"
        f"Clinical data (JSON):\n{raw_clinical_text}\n\n"
        f"Please translate this for a {target_audience}."
    )
    return _call_llm(prompt)


def _call_llm(prompt: str) -> str:
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise LLMConfigError("ANTHROPIC_API_KEY is not set")
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
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
            max_tokens=1024,
        )
        return response.choices[0].message.content
    else:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. Use 'anthropic' or 'openai'."
        )
