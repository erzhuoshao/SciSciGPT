from typing import Literal
from langgraph.graph import END, START, StateGraph
from functools import partial
from agents.nodes import call_research_manager, call_specialist, call_toolset, call_specialistset, AgentState
from agents.evaluation import call_evaluation
from agents.compaction import call_compactor, should_compact

import pickle
import os
from datetime import datetime

def select_next(state: AgentState, verbose: bool = False) -> Literal[
	"node_research_manager", "node_database_specialist", "node_analytics_specialist", "node_literature_specialist",
	"node_evaluation_specialist", "node_specialistset", "node_toolset", "node_compactor", END]:

	current, next = state["current"], state["next"]
	target = next.split(":")[0]

	# End of turn: if the ResearchManager's context has crossed the budget
	# threshold, compact the history before finishing (never after a
	# compaction itself, so a single pass per turn).
	if target == END and current != "compaction" and should_compact(state):
		return "node_compactor"

	return target

from agents.specialists import database_specialist as DS
from agents.specialists import analytics_specialist as AS
from agents.specialists import literature_specialist as LS
from agents.specialists import evaluation_specialist as ES

all_tools = [ *DS.tools, *AS.tools, *LS.tools, *ES.tools ]
all_specialists = [DS, AS, LS, ES]


from agents.utils.messages import _remove_xml_tags_from_messages
pruning_func = partial(_remove_xml_tags_from_messages, tags=["thinking"])
identity_func = lambda x: x


def define_sciscigpt_graph(load_llm):
	node_research_manager = partial(
		call_research_manager, load_llm, [DS, AS, LS], pruning_func)

	# Chain-of-thought is write-only: <thinking> is dropped from every
	# downstream LLM input (specialists and evaluators alike) to keep
	# contexts clean of stale reasoning.
	node_database_specialist = partial(call_specialist, load_llm, DS.tools + [ES], pruning_func)
	node_analytics_specialist = partial(call_specialist, load_llm, AS.tools + [ES], pruning_func)
	node_literature_specialist = partial(call_specialist, load_llm, LS.tools + [ES], pruning_func)
	node_evaluation_specialist = partial(call_evaluation, load_llm, [DS, AS, LS], pruning_func)

	node_specialistset = partial(call_specialistset, [DS, AS, LS])
	node_toolset = partial(call_toolset, [ *DS.tools, *AS.tools, *LS.tools ])
	node_compactor = partial(call_compactor, load_llm)

	sciscigpt_graph = StateGraph(AgentState)
	sciscigpt_graph.add_node("node_research_manager", node_research_manager)
	sciscigpt_graph.add_node("node_database_specialist", node_database_specialist)
	sciscigpt_graph.add_node("node_analytics_specialist", node_analytics_specialist)
	sciscigpt_graph.add_node("node_literature_specialist", node_literature_specialist)
	sciscigpt_graph.add_node("node_evaluation_specialist", node_evaluation_specialist)
	sciscigpt_graph.add_node("node_specialistset", node_specialistset)
	sciscigpt_graph.add_node("node_toolset", node_toolset)
	sciscigpt_graph.add_node("node_compactor", node_compactor)

	sciscigpt_graph.add_edge(START, "node_research_manager")
	sciscigpt_graph.add_conditional_edges("node_research_manager", select_next)
	sciscigpt_graph.add_conditional_edges("node_database_specialist", select_next)
	sciscigpt_graph.add_conditional_edges("node_analytics_specialist", select_next)
	sciscigpt_graph.add_conditional_edges("node_literature_specialist", select_next)
	sciscigpt_graph.add_conditional_edges("node_evaluation_specialist", select_next)
	sciscigpt_graph.add_conditional_edges("node_specialistset", select_next)
	sciscigpt_graph.add_conditional_edges("node_toolset", select_next)
	sciscigpt_graph.add_conditional_edges("node_compactor", select_next)

	return sciscigpt_graph


__all__ = [
	"AgentState", "all_tools", "all_specialists", "define_sciscigpt_graph"
]