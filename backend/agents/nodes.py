import json
from typing import Annotated, Dict, Any, TypedDict, Literal

from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage, AIMessage

from agents.prompts import research_manager_prompt, specialist_prompt_dict
from agents.utils.agent_state import AgentState
from agents.utils.messages import _extract_task_from_message, _extract_workflows_from_messages, _format_workflow
from agents.utils.messages import _remove_xml_tags_from_messages, _extract_xml_tags_from_text
from agents.utils.messages import _filter_rm_visible_messages, _mark_cache_control

from agents.utils.messages import return_messages


def call_research_manager(load_llm, tools, pruning_func, state: AgentState):
	profile = {"current": "research_manager", "name": "call_research_manager"}
	try:
		llm = load_llm(state["metadata"], disable_streaming=False)
		tools_by_name = {tool.name: tool for tool in tools}

		human_message = HumanMessage(content="""
		Decide your next step:
		1. If the request is ambiguous in a way that changes what should be done, ask the user to clarify and stop.
		2. If further work is needed, assign the next task to exactly one of database_specialist, analytics_specialist, literature_specialist via a complete <task_brief>.
		3. If the user request has been fully addressed, synthesize the final answer in <answer> tags.""")

		input_messages = pruning_func([
			*research_manager_prompt.invoke({}).messages,
			*_remove_xml_tags_from_messages(_filter_rm_visible_messages(state['messages']), ["thinking"]),
			human_message
		])

		tags = ["node_research_manager"]
		response = llm.bind_tools(
			list(tools_by_name.values()),
			tool_choice = { "type": "auto", "disable_parallel_tool_use": True }
		).invoke(
			_mark_cache_control(input_messages), config={"tags": tags}
		)
		response.tags = tags

		if len(response.tool_calls) == 0:
			next = END
		else:
			next = "node_specialistset"

	except Exception as e:
		response = AIMessage(content="{}: {}".format(type(e).__name__, str(e)))
		next = END
	
	return return_messages([response], next=next, **profile)


from functools import reduce
def call_specialist(load_llm, tools, pruning_func, state: AgentState):
	task = _extract_task_from_message(state["messages"])
	specialist, task, memory = task["specialist"], task["task"], task["memory"]
	profile = {"current": specialist, "name": "call_specialist"}

	try:
		llm = load_llm(state["metadata"], disable_streaming=False)
		
		workflows = _extract_workflows_from_messages(state["messages"], specialist, newest=False)
		historical_workflows, newest_workflow = workflows[:-1], workflows[-1]
		historical_workflows = [_format_workflow(w) for w in historical_workflows]
		historical_messages = [m for w in historical_workflows for m in w] if memory else []
		newest_messages = _format_workflow(newest_workflow)

		assert specialist in specialist_prompt_dict, f"Invalid specialist: {specialist}. Only {list(specialist_prompt_dict.keys())} are allowed."
		system_messages = specialist_prompt_dict[specialist].invoke({}).messages
		input_messages = pruning_func([ *system_messages, *historical_messages, *newest_messages ])

		# Claude 4.6+ removed assistant-message prefill: the API rejects requests
		# whose last message is an assistant turn (400). After an evaluation turn
		# the workflow ends with the evaluator's AIMessage, so close it with a
		# user turn instructing the specialist to continue.
		if input_messages and isinstance(input_messages[-1], AIMessage):
			input_messages.append(HumanMessage(content="""
			Continue the task, taking the evaluation feedback above into account.
			If the task is fully complete, end with your <handoff> block and call `evaluation_specialist`."""))

		tags = [specialist]
		response = llm.bind_tools(
			tools, tool_choice = { "type": "auto", "disable_parallel_tool_use": True }
		).invoke( _mark_cache_control(input_messages), config={ "tags": tags } )
		response.content = response.text
		response.tags = tags

		# If any tool call generated, continue the task (reasoning - tool call iteration)
		if response.tool_calls and response.tool_calls[0]["name"] != "evaluation_specialist":
			next = "node_toolset"

			tool_name = response.tool_calls[0]["name"]
			messages = [response]

		# If no further tool call, end this task, pass to evaluation_specialist
		else:
			next = "node_evaluation_specialist:task_eval"

			response_str = response.text
			if len(response_str) > 0:
				response.tool_calls = []
				response.content = response_str
				messages = [response]
			else:
				messages = []


	except Exception as e:
		next = "node_evaluation_specialist:task_eval"

		response = AIMessage(content="{}: {}".format(type(e).__name__, str(e)))
		messages = [response]
		

	return return_messages(messages, next=next, **profile)



from func.image import if_message_contains_image
def call_toolset(tools, state: AgentState):
	try:
		tools_by_name = {tool.name: tool for tool in tools}
		tool_call = state["messages"][-1].tool_calls[0]
		tool_name, tool_call_id, tool_args = tool_call["name"], tool_call["id"], tool_call["args"]

		profile = {"current": tool_name, "name": "call_toolset"}

		assert tool_name in tools_by_name, f"Invalid tool: {tool_name}. Only {list(tools_by_name.keys())} are allowed."
		required_args = tools_by_name[tool_name].args_schema.schema()["properties"].keys()
		tool_args = {k: v for k, v in tool_args.items() if k in required_args}
		# Backfill schema defaults for args the model omitted: langchain>=1.x only
		# forwards keys present in the original input to _run, so an omitted arg
		# with a default (e.g. sql_list_table's `query`) raises TypeError.
		for k, spec in tools_by_name[tool_name].args_schema.schema()["properties"].items():
			if k not in tool_args and "default" in spec:
				tool_args[k] = spec["default"]
		tool_args["state"] = state

		tags = ["toolset", tool_name]
		results = tools_by_name[tool_name].invoke(tool_args, config={ "tags": tags })
		results = json.loads(results) if isinstance(results, str) else results
		tool_message = ToolMessage(content=[{"type": "text", "text": json.dumps(results)}], tool_call_id=tool_call_id, tags=tags)

		visual = if_message_contains_image(tool_message)
		next = "node_evaluation_specialist:visual_eval" if visual else "node_evaluation_specialist:tool_eval"

	except Exception as e:
		profile = {"current": "toolset", "name": "call_toolset"}

		results = { "response": "{}: {}".format(type(e).__name__, str(e)) }
		tool_message = ToolMessage(content=[{"type": "text", "text": json.dumps(results)}], tool_call_id=tool_call_id, tags=["toolset"])
		next = "node_evaluation_specialist:tool_eval"

	return return_messages([tool_message], next=next, **profile)


def call_specialistset(specialists, state: AgentState):
	profile = {"current": "specialistset", "name": "call_specialistset"}

	try:
		specialists_by_name = {specialist.name: specialist for specialist in specialists}
		specialist_call = state["messages"][-1].tool_calls[0]
		specialist_name, specialist_call_id, specialist_args = specialist_call["name"], specialist_call["id"], specialist_call["args"]

		assert specialist_name in specialists_by_name, f"Invalid specialist: {specialist_name}. Only {list(specialists_by_name.keys())} are allowed."
		results = specialists_by_name[specialist_name].invoke(specialist_args)

		specialist_message = ToolMessage(content=[{"type": "text", "text": json.dumps(results)}], tool_call_id=specialist_call_id)
		next = f"node_{specialist_name}"

	except Exception as e:
		results = { "response": "{}: {}".format(type(e).__name__, str(e)) }
		specialist_message = ToolMessage(content=[{"type": "text", "text": json.dumps(results)}], tool_call_id=specialist_call_id)
		next = "node_evaluation_specialist:task_eval"

	return return_messages([specialist_message], next=next, **profile)