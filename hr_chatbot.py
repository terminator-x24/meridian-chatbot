"""Meridian HR chatbot: Groq + Streamlit (AI DataYard, AI Automation Bootcamp, Module 2).

Fictional company and fictional data only.

How it runs: this file lives in a GitHub repo and is deployed with Streamlit Community Cloud.
Key:         add GROQ_API_KEY to the app's Secrets settings. Never type the key into this file.
On your own computer instead: pip install streamlit openai, put the key in
.streamlit/secrets.toml, then run  streamlit run hr_chatbot.py
"""
import json
import os
import re

import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------------- settings
POLICY_VERSION = "2026.1"
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")  # Groq retires models: check console.groq.com/docs/models
BASE_URL = "https://api.groq.com/openai/v1"  # Groq's API works with the OpenAI Python library

POLICY = {
    "1.1": "Annual leave: 20 paid days per calendar year, accrued monthly.",
    "1.2": "Carry forward: Up to 5 unused annual leave days carry into the next year; the rest lapse on 31 March.",
    "1.3": "Leave notice: 1 to 5 days: 3 working days' notice. More than 5 consecutive days: 14 days' notice. "
           "All annual leave needs line manager approval.",
    "2.1": "Sick leave: 10 paid days per year. A medical certificate is required for absences of "
           "2 or more consecutive days.",
    "3.1": "Working hours: 9:00 to 18:00, Monday to Friday, with a 15-minute grace period.",
    "3.2": "Remote work: Up to 2 days per week with line manager approval. Additional days need HR approval.",
    "4.1": "Health insurance: Covers the employee, spouse and up to 2 children.",
    "5.1": "Confidentiality: HR does not disclose other employees' pay or personal data.",
}

# Step 2 of the workflow pattern (prepare context): pick only the section(s) that apply.
KEYWORDS = {
    "1.1": ["annual leave"],
    "1.2": ["carry", "lapse"],
    "1.3": ["notice", "days off", "take leave", "time off"],
    "2.1": ["sick", "doctor", "medical"],
    "3.1": ["working hours", "start time", "grace"],
    "3.2": ["work from home", "remote", "wfh"],
    "4.1": ["insurance"],
    "5.1": ["salary", "pay"],
}


def pick_sections(question):
    q = question.lower()
    return [sid for sid, words in KEYWORDS.items() if any(w in q for w in words)]


# ---------------------------------------------------------------- TODO 1: the reusable prompt
PROMPT_TEMPLATE = """You are an HR assistant. Answer this question: {{question}}"""
# TODO 1: rewrite PROMPT_TEMPLATE using the Lab 1 instructions and these three placeholders:
#   {{policy_version}}  {{policy_text}}  {{question}}
# It must tell the model to answer only from the policy text and to return the five JSON fields.


def build_prompt(question):
    ids = pick_sections(question)
    text = "\n".join(f"{sid} {POLICY[sid]}" for sid in ids) or "(no matching section found)"
    return (PROMPT_TEMPLATE
            .replace("{{policy_version}}", POLICY_VERSION)
            .replace("{{policy_text}}", text)
            .replace("{{question}}", question))


# ---------------------------------------------------------------- TODO 2: validation rules
FIELDS = ["answer", "policy_section", "answer_found", "needs_human", "escalation_reason"]
SENSITIVE = ["unfair", "harass", "complain", "grievance", "fired", "terminat", "salary", "pay cut", "colleague"]


def clean(raw):
    """Remove code fences if the model wrapped its JSON in them."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    return re.sub(r"```$", "", text).strip()


def validate(question, raw):
    """Return (data, problem). problem is None when every rule passes."""
    # Rule 1 is done for you: valid JSON with all five fields.
    try:
        data = json.loads(clean(raw))
    except (json.JSONDecodeError, TypeError):
        return None, "not valid JSON"
    if not isinstance(data, dict) or any(f not in data for f in FIELDS):
        return None, "a required field is missing"

    # TODO 2: add the other three rules from your Lab 3 sheet. Return (None, "reason") when one fails.
    #   Rule 2: answer_found is true only when policy_section is filled.
    #   Rule 3: if the question holds a word from SENSITIVE, force data["needs_human"] to True.
    #   Rule 4: numbers in the answer must appear in the cited section (or in the question).
    return data, None


# ---------------------------------------------------------------- TODO 3: the message to HR
def hr_message(question, data, problem=None):
    # TODO 3: write the message sent to HR. It needs the question, the reason and any section found.
    return f"Question: {question}"


# ---------------------------------------------------------------- calling the model
def get_key():
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return None


def call_model(prompt):
    client = OpenAI(api_key=get_key(), base_url=BASE_URL, timeout=30)
    reply = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return reply.choices[0].message.content


RETRY_NOTE = "\n\nReturn only valid JSON."


def answer_question(question):
    """Run the workflow: prepare context, call the model, validate. Returns (data, problem)."""
    prompt = build_prompt(question)
    data, problem = None, "no reply"
    for attempt in range(2):
        try:
            raw = call_model(prompt if attempt == 0 else prompt + RETRY_NOTE)
        except Exception as error:  # slow reply, usage limit, bad key
            return None, f"the model call failed ({type(error).__name__})"
        data, problem = validate(question, raw)
        # Retry once only when the output was not valid JSON with all fields.
        if problem is None or not problem.startswith(("not valid JSON", "a required field")):
            break
    return data, problem


# ---------------------------------------------------------------- the app
def main():
    st.set_page_config(page_title="Meridian HR assistant")
    st.title("Meridian HR assistant")
    st.caption(f"Fictional company. Answers come only from policy version {POLICY_VERSION}.")

    if not get_key():
        st.error("No API key found. Add GROQ_API_KEY to the app's Secrets settings, then reboot the app.")
        st.stop()

    if "chat" not in st.session_state:
        st.session_state.chat = []
        st.session_state.queue = []
        st.session_state.last = None

    for role, text in st.session_state.chat:
        with st.chat_message(role):
            st.write(text)

    question = st.chat_input("Ask an HR question")
    if question:
        st.session_state.chat.append(("user", question))
        with st.chat_message("user"):
            st.write(question)

        data, problem = answer_question(question)
        st.session_state.last = data

        if data is not None and data["answer_found"] and data["answer"]:
            reply = str(data["answer"])
            if data["needs_human"]:
                st.session_state.queue.append(hr_message(question, data, problem))
                reply += "\n\nI have also passed your question to HR to confirm."
        else:
            st.session_state.queue.append(hr_message(question, data, problem))
            reply = "I have passed your question to HR. They will reply to you soon."

        st.session_state.chat.append(("assistant", reply))
        with st.chat_message("assistant"):
            st.write(reply)

    with st.sidebar:
        st.header("HR queue")
        if not st.session_state.queue:
            st.write("Nothing escalated yet.")
        for message in st.session_state.queue:
            st.code(message, language=None)
        with st.expander("Last structured answer"):
            st.json(st.session_state.last or {})


if __name__ == "__main__":
    main()
