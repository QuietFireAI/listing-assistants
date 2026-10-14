"""model_drafting - Agent 04's optional model-written listing remarks.

Added 2026-10-12 (owner: wire the optional modules). Before this, the Hermes
seam and the checkpoint manager were called by nothing in the swarm.

How it is wired
  build_swarm(model_client=..., model_name=...) puts a DraftingModel on the
  hub as hub.drafting. Agent 04 uses it only when ALL of these hold:
    1. the broker signed {"drafting": {"mode": "model"}} to Agent 04
       (default "rules": 04's deterministic facts-only draft, unchanged);
    2. a model client is configured for this process;
    3. the ACTIVE checkpoint in the checkpoint manifest passed the broker
       exam (dispatcher/model_checkpoint_manager.py) on THIS served model.
       The shipped baseline has never been examined, so nothing is drafted
       by a model until the broker runs the exam
       (tools/restore_point.py --exam --model-url ... --model-name ...).
  When any condition fails, 04 drafts by rules, records why on the chain
  (drafting.model_unavailable) and tells the broker.

What a model draft must pass before it goes to compliance (17)
  - the model produced its reasoning (<think>); an empty reasoning trips the
    agent-open-mind taint gate on the hub and the draft is not used;
  - it fits the MLS character limit;
  - every number in it, in digits or spelled out, appears in the listing
    facts (a model cannot add a bedroom count, a square footage or a year
    that the data does not have).
  It does NOT check that every word is supported by the data: a model can
  still describe a feature in words the facts do not contain. That is why
  model remarks ride next to the facts in the same draft, go through 17's
  fair-housing review like every draft, and are labeled with their source.

The model client
  OpenAICompatibleClient talks to an OpenAI-style /chat/completions endpoint
  (Ollama: http://localhost:11434/v1). It refuses any host other than this
  machine unless allow_remote=True, because the prompt carries listing data.
  The Hermes learning loop is not run on live drafts.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from types import SimpleNamespace
from typing import Any, Optional

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
_WORDS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
               "eighty": "80", "ninety": "90", "single": "1", "double": "2", "twin": "2"})
_WORD = re.compile(r"[a-z]+")


def numbers_in(text: str) -> set:
    """Digits and spelled-out numbers ('four' -> '4'). Compound words count
    part by part ('twenty-five' -> 20 and 5), which can reject a correct
    draft; it never lets a new number through."""
    found = {n.replace(",", "") for n in _NUMBER.findall(text)}
    found |= {_WORDS[w] for w in _WORD.findall(text.lower()) if w in _WORDS}
    return found


def served_adapter_path(model_name: str) -> str:
    """The checkpoint 'adapter path' for a served model: no weights ship; the
    exam result is bound to the model name it was run against."""
    return f"builtin://served/{model_name}"


class OpenAICompatibleClient:
    """client.chat.completions.create(model=..., messages=[...]) over HTTP."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: float = 120.0,
                 allow_remote: bool = False):
        host = urllib.parse.urlparse(base_url).hostname or ""
        if host not in _LOCAL_HOSTS and not allow_remote:
            raise ValueError(f"model endpoint host {host!r} is not this machine; listing data "
                             f"would leave it - pass allow_remote=True only if you mean that")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model: str, messages: list, **kw):
        body = json.dumps({"model": model, "messages": messages, "temperature": 0,
                           "stream": False}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body,
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 (host checked)
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class DraftingModel:
    def __init__(self, hub: Any, client: Any, model_name: str, checkpoints_dir: str):
        from .hermes_seam import HermesCognitiveSeam
        from .model_checkpoint_manager import ModelCheckpointManager
        self.hub = hub
        self.client = client
        self.model_name = model_name
        self.checkpoints = ModelCheckpointManager(checkpoints_dir)
        self.seam = HermesCognitiveSeam(hub=hub, client=client, model=model_name)

    # ---------------------------------------------------------------- gate
    def gate(self) -> dict:
        if self.client is None:
            return {"ok": False, "reason": "no model client configured in this process"}
        active = self.checkpoints.get_active_checkpoint()
        cid = active.get("checkpoint_id")
        if active.get("exam_passed") is not True:
            return {"ok": False, "checkpoint": cid,
                    "reason": f"active checkpoint {cid!r} has not passed the broker exam"}
        if active.get("adapter_path") != served_adapter_path(self.model_name):
            return {"ok": False, "checkpoint": cid,
                    "reason": f"active checkpoint {cid!r} was examined on "
                              f"{active.get('adapter_path')!r}, not on {self.model_name!r}"}
        return {"ok": True, "checkpoint": cid}

    # ---------------------------------------------------------------- exam
    def _ask(self, question: str) -> str:
        r = self.client.chat.completions.create(model=self.model_name, messages=[
            {"role": "system", "content": "You are a licensed real estate brokerage assistant."},
            {"role": "user", "content": question}])
        _thinking, text = self.seam.parse_hermes_output(r.choices[0].message.content or "")
        return text

    def examine(self, checkpoint_id: str, activate: bool = True) -> dict:
        """Runs the broker exam against the served model, registers the
        result, and activates it only if it passed."""
        if self.client is None:
            raise RuntimeError("no model client configured - nothing to examine")
        entry = self.checkpoints.register_checkpoint(
            checkpoint_id, served_adapter_path(self.model_name),
            notes=f"exam run against served model {self.model_name!r}", test_responder=self._ask)
        if activate and entry["exam_passed"] is True:
            entry = self.checkpoints.activate_checkpoint(checkpoint_id)
        return entry

    # ---------------------------------------------------------------- draft
    def draft_remarks(self, agent_id: str, envelope_id: str, facts: list[dict],
                      char_limit: int) -> dict:
        g = self.gate()
        if not g["ok"]:
            return g
        lines = [f"- {f['text']}" + (f" ({f['attribution']})" if f.get("attribution") else "")
                 for f in facts]
        prompt = (f"Write MLS public remarks for a listing in at most {char_limit} characters. "
                  f"Use ONLY these facts; keep every attribution; add no number, feature, "
                  f"neighborhood, school, or description of who would like the home:\n"
                  + "\n".join(lines))
        # MANNERS on every model call (owner decision 2026-10-14): the one
        # model prompt in this product carries the conduct rules
        manners = getattr(self.hub, "manners", None)
        if manners is not None:
            prompt = manners.prompt_block() + "\n" + prompt
        from .hermes_seam import HermesUnavailableError
        try:
            thinking, text = self.seam.draft_and_trace(agent_id, envelope_id, prompt, learn=False)
        except HermesUnavailableError as e:
            return {"ok": False, "checkpoint": g["checkpoint"], "reason": str(e)}
        text = (text or "").strip()
        if not thinking.strip():
            return {"ok": False, "checkpoint": g["checkpoint"],
                    "reason": "model gave no reasoning (<think>) - taint gate tripped, draft not used"}
        if not text:
            return {"ok": False, "checkpoint": g["checkpoint"], "reason": "model returned empty remarks"}
        if len(text) > char_limit:
            return {"ok": False, "checkpoint": g["checkpoint"],
                    "reason": f"model remarks are {len(text)} characters (limit {char_limit})"}
        allowed = set().union(*(numbers_in(f["text"]) for f in facts)) if facts else set()
        added = sorted(numbers_in(text) - allowed)
        if added:
            return {"ok": False, "checkpoint": g["checkpoint"],
                    "reason": f"model added numbers not in the listing data: {added}"}
        return {"ok": True, "checkpoint": g["checkpoint"], "remarks": text}
