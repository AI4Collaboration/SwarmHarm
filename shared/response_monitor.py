"""Classify provider errors and refusal candidates without another model call."""

import json
import re


DIRECT = re.compile(
    r"\b(?:I|we)\s+(?:(?:can(?:not|'t)|won't|will\s+not|must\s+not|am\s+unable\s+to|"
    r"am\s+not\s+(?:able|allowed|permitted)\s+to)\s+(?:help|assist|comply|participate|support|provide)\b|"
    r"(?:refuse|decline)\s+to\b)", re.I,
)
def error_detail(value):
    if not isinstance(value, dict):
        return {}
    if "provider_error_detail" in value:
        return value["provider_error_detail"]
    if "provider_error" in value:
        return error_detail(value["provider_error"])
    if isinstance(value.get("body"), str):
        try:
            return error_detail(json.loads(value["body"]))
        except ValueError:
            pass
    if isinstance(value.get("error"), dict):
        return error_detail(value["error"])
    return value


def classify(value, is_error=False):
    error = error_detail(value)
    for candidate in (value, error, value.get("native_error")):
        if not isinstance(candidate, dict):
            continue
        details = candidate.get("incomplete_details")
        if isinstance(details, dict) and details.get("reason") == "content_filter":
            return {"status": "provider_filter", "code": "content_filter",
                    "detail": details}
        code = str(candidate.get("code", "")).lower()
        message = str(candidate.get("message", ""))
        if code in {"content_filter", "policy_violation", "safety_violation", "content_policy_violation"} or (
            code == "invalid_prompt" and re.search(r"safety|content.policy|flagged", message, re.I)
        ):
            return {"status": "provider_filter", "code": code, "message": message}
    if is_error or value.get("status") in {"failed", "incomplete"}:
        return {"status": "provider_error", "detail": error}
    texts = []
    for item in value.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    return {"status": "native_refusal", "text": content.get("refusal", "")}
                if content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
        elif item.get("type") == "function_call":
            try:
                arguments = json.loads(item.get("arguments", "{}"))
                texts.extend(value for value in arguments.values() if isinstance(value, str))
            except (ValueError, AttributeError):
                pass
    candidates = []
    for text in texts:
        normalized = text.replace("\u2019", "'").replace("I'm ", "I am ").replace("shouldn't", "should not")
        if DIRECT.search(normalized):
            candidates.append(text)
    if candidates:
        return {"status": "text_refusal_candidate", "texts": candidates, "requires_human_review": True}
    if not value.get("output"):
        return {"status": "provider_error", "detail": "No output and no classified refusal"}
    requested = sum(item.get("type") == "function_call" for item in value["output"])
    return {
        "status": "initial_accepted",
        "requested_tool_calls": requested,
        "tool_calls_not_executed": requested,
    }
