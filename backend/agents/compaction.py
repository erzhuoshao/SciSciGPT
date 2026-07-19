import os
import re

from langchain_core.messages import AIMessage, HumanMessage

from agents.prompts import compactor_prompt
from agents.utils.agent_state import AgentState
from agents.utils.messages import _apply_compaction, _filter_rm_visible_messages, _remove_xml_tags_from_messages
from agents.utils.messages import return_messages

COMPACT_ENABLED = os.getenv("COMPACT_ENABLED", "true").lower() == "true"
COMPACT_THRESHOLD = float(os.getenv("COMPACT_THRESHOLD", "0.4"))
COMPACT_CONTEXT_BUDGET_TOKENS = int(os.getenv("COMPACT_CONTEXT_BUDGET_TOKENS", "200000"))


def should_compact(state: AgentState) -> bool:
	"""Decide at end-of-turn whether to compact: the ResearchManager's last call
	carries its exact billed context size in usage_metadata.input_tokens."""
	if not COMPACT_ENABLED:
		return False
	messages = state.get("messages") or []
	if not messages:
		return False
	usage = getattr(messages[-1], "usage_metadata", None) or {}
	input_tokens = usage.get("input_tokens") or 0
	return input_tokens >= COMPACT_THRESHOLD * COMPACT_CONTEXT_BUDGET_TOKENS


def call_compactor(load_llm, state: AgentState):
	profile = {"current": "compaction", "name": "call_compactor"}
	try:
		llm = load_llm(state["metadata"], disable_streaming=False)

		visible = _remove_xml_tags_from_messages(
			_filter_rm_visible_messages(_apply_compaction(state["messages"])), ["thinking"])
		instruction = HumanMessage(content=compactor_prompt.invoke({}).messages[0].content)

		tags = ["node_compactor"]
		response = llm.invoke([*visible, instruction], config={"tags": tags})

		summary = response.text
		match = re.search(r"<compaction_summary>.*?</compaction_summary>", summary, re.DOTALL)
		summary = match.group(0) if match else f"<compaction_summary>\n{summary}\n</compaction_summary>"

		message = AIMessage(content=summary)
		return return_messages([message], next="__end__", **profile)

	except Exception:
		# Compaction is best-effort: never block the turn; retry next time.
		return return_messages([], next="__end__", **profile)
