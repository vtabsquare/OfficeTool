# ai_hf.py - Hugging Face Inference AI integration for HR Office Tool
import os
import json
from typing import Optional, List, Dict, Any

import requests
from dotenv import load_dotenv

# Load local env file for dev (ignored in Render if not present)
load_dotenv("id.env")

HF_API_KEY = os.getenv("HF_API_KEY") or os.getenv("HUGGINGFACE_API_KEY")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3")
# Use the new router endpoint (api-inference.huggingface.co is deprecated)
HF_API_URL = f"https://router.huggingface.co/hf-inference/models/{HF_MODEL_ID}"


def build_system_prompt(user_meta: Dict[str, Any]) -> str:
    """Build a system prompt for the HR AI assistant (same semantics as Gemini version)."""
    user_name = user_meta.get("name", "User")
    user_role = "Admin" if user_meta.get("is_admin") else "Employee"
    emp_id = user_meta.get("employee_id", "Unknown")

    return f"""You are an intelligent HR Assistant for VTab Office Tool. You help employees and managers with HR-related queries.

Current User: {user_name} ({emp_id}) - Role: {user_role}

Your capabilities:
- Answer questions about attendance, leaves, timesheets, and HR policies
- Provide summaries of employee data and team statistics
- Help with leave applications, attendance queries, and timesheet information
- Explain HR processes and company policies
- Analyze trends in attendance and leave patterns

Guidelines:
1. Be concise, professional, and helpful
2. Use the provided data context to give accurate answers
3. If data is not available, clearly state that
4. For sensitive information, respect user permissions
5. Format responses with clear structure when appropriate
6. Use bullet points and numbers for lists
7. Be friendly but professional

You only have access to the data provided in the context. Do not invent data."""


def _build_full_prompt(question: str, data_context: Dict[str, Any], user_meta: Dict[str, Any], history: Optional[List[Dict[str, Any]]]) -> str:
    system_prompt = build_system_prompt(user_meta)

    # Build context from data
    context_parts: List[str] = []
    if data_context:
        context_parts.append("=== AVAILABLE DATA (from Dataverse) ===")
        for key, value in data_context.items():
            if value:
                if isinstance(value, (dict, list)):
                    context_parts.append(f"\n{key.upper()}:\n{json.dumps(value, indent=2, default=str)}")
                else:
                    context_parts.append(f"\n{key.upper()}: {value}")

    context_str = "\n".join(context_parts) if context_parts else "No specific data available."

    # Optional short conversation history
    history_lines: List[str] = []
    if history:
        for msg in history[-6:]:  # keep last few turns
            role = "User" if msg.get("role") == "user" else "Assistant"
            text = (msg.get("text") or "").strip()
            if text:
                history_lines.append(f"{role}: {text}")

    history_block = ("\n\nPrevious conversation:\n" + "\n".join(history_lines)) if history_lines else ""

    full_prompt = f"""{system_prompt}

{context_str}

User Question: {question}
{history_block}

Please provide a clear, concise, and accurate answer based only on the information above. If something is unknown, say so explicitly."""
    return full_prompt


def ask_hf(
    question: str,
    data_context: Dict[str, Any],
    user_meta: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Send a question to a Hugging Face text-generation model and get a response.

    Returns a dict with keys: success (bool), answer (str|None), error (str|None).
    """
    if not HF_API_KEY:
        return {
            "success": False,
            "answer": None,
            "error": "HF_API_KEY is not configured on the server. Please set it in the environment.",
        }

    full_prompt = _build_full_prompt(question, data_context, user_meta, history)

    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "inputs": full_prompt,
        "parameters": {
            "max_new_tokens": 512,
            "temperature": 0.7,
            "top_p": 0.95,
            "do_sample": True,
            "return_full_text": False,  # Don't echo the prompt
        },
    }

    try:
        resp = requests.post(HF_API_URL, headers=headers, json=payload, timeout=60)

        if resp.status_code != 200:
            # HF often returns {"error": "..."} JSON; include a short snippet for debugging
            text_snippet = resp.text[:300]
            return {
                "success": False,
                "answer": None,
                "error": f"Hugging Face API error {resp.status_code}: {text_snippet}",
            }

        result = resp.json()

        generated = ""
        if isinstance(result, list) and result:
            # Inference API returns a list of candidates
            item = result[0] or {}
            generated = (item.get("generated_text") or "").strip()
        elif isinstance(result, dict):
            generated = (result.get("generated_text") or "").strip()

        if not generated:
            return {
                "success": False,
                "answer": None,
                "error": "Empty response from Hugging Face model",
            }

        # Many models echo the prompt; try to remove it if present
        answer = generated
        if full_prompt in generated:
            answer = generated.split(full_prompt, 1)[-1].strip()

        if not answer:
            answer = generated

        return {
            "success": True,
            "answer": answer.strip(),
            "error": None,
        }

    except requests.Timeout:
        return {
            "success": False,
            "answer": None,
            "error": "Hugging Face request timed out. Please try again.",
        }
    except Exception as exc:
        return {
            "success": False,
            "answer": None,
            "error": f"Unexpected Hugging Face error: {exc}",
        }


def quick_answer(question: str, user_name: str = "User") -> str:
    """Quick helper for simple questions without full context (for testing)."""
    result = ask_hf(
        question=question,
        data_context={},
        user_meta={"name": user_name, "is_admin": False},
        history=None,
    )
    return result.get("answer") or result.get("error", "Unable to get response")
