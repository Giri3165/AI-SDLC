import json
from flask import current_app
import anthropic


def suggest_tasks_for_requirement(title, description):
    """
    Asks Claude to break a requirement down into concrete development
    tasks. Returns a list of {"title": ..., "description": ...} dicts,
    or None if the feature isn't configured or the call failed.

    This is deliberately advisory-only: nothing is written to the
    database here. The manager reviews the suggestions and creates
    whichever tasks they actually want through the normal task-creation
    flow (which still requires picking a real developer and priority).
    """
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        current_app.logger.warning(
            "AI task suggestions unavailable: ANTHROPIC_API_KEY not set in .env"
        )
        return None

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are helping a software project manager break a requirement into concrete development tasks.

Requirement title: {title}
Requirement description: {description or "No additional description provided."}

Suggest 3 to 6 concrete, specific development tasks needed to implement this requirement.
Respond with ONLY a JSON array, no other text, no markdown code fences.
Each item must be an object with exactly two string fields: "title" and "description".
Example format: [{{"title": "...", "description": "..."}}]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        # Defensive cleanup in case the model wraps the JSON in fences
        # despite being asked not to.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:].strip()

        tasks = json.loads(raw_text)

        if not isinstance(tasks, list):
            raise ValueError("AI response was not a JSON array")

        cleaned = []
        for item in tasks:
            if isinstance(item, dict) and item.get("title"):
                cleaned.append({
                    "title": str(item.get("title", "")).strip(),
                    "description": str(item.get("description", "")).strip()
                })

        return cleaned if cleaned else None

    except Exception as e:
        current_app.logger.error(f"AI task suggestion failed: {e}")
        return None


def generate_release_notes(project_name, completed_tasks):
    """
    Asks Claude to turn a list of completed dev tasks into a short,
    client-readable "What's New" summary — no technical jargon, no
    bullet-point task titles verbatim, just plain English.

    completed_tasks: list of {"title": ..., "description": ...} dicts.
    Returns a string, or None if unavailable/failed. Callers should fall
    back to leaving the notes field blank or using the manager's own
    text, never block on this.
    """
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        current_app.logger.warning(
            "AI release notes unavailable: ANTHROPIC_API_KEY not set in .env"
        )
        return None

    if not completed_tasks:
        return None

    client = anthropic.Anthropic(api_key=api_key)

    task_lines = "\n".join(
        f"- {t['title']}: {t.get('description', '')}".strip(": ")
        for t in completed_tasks
    )

    prompt = f"""You are writing release notes for a non-technical client, for a software project called "{project_name}".

Here is the internal list of development work completed for this release:
{task_lines}

Write a short, friendly "What's New" summary in plain English (2-4 sentences).
No bullet points, no technical jargon, no internal task names verbatim — describe
the value/outcome for the client instead. Positive, professional tone.
Respond with ONLY the summary text, nothing else."""

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        return text if text else None

    except Exception as e:
        current_app.logger.error(f"AI release notes generation failed: {e}")
        return None
