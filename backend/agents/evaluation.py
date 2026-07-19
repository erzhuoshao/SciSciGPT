from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json

from agents.nodes import AgentState
from agents.prompts import tool_eval_prompt, visual_eval_prompt, task_eval_prompt
from agents.utils.messages import _extract_task_from_message, _extract_workflows_from_messages, _format_workflow
from agents.utils.messages import _extract_xml_tags_from_text

from agents.utils.images import _multimodal_message
from agents.utils.messages import return_messages


async def call_evaluation(load_llm, specialists, pruning_func, state: AgentState):
	llm = load_llm(state["metadata"], disable_streaming=False)
	specialists_by_name = {specialist.name: specialist for specialist in specialists}

	task = _extract_task_from_message(state["messages"])
	specialist = task["specialist"]

	model = llm.bind_tools(specialists_by_name[specialist].tools)

	eval_type = state["next"].split(":")[1]
	assert eval_type in ["task_eval", "visual_eval", "tool_eval"], f"Invalid evaluation type: {eval_type}"


	task = _extract_task_from_message(state["messages"])
	specialist, task, memory = task["specialist"], task["task"], task["memory"]

	workflows = _extract_workflows_from_messages(state["messages"], specialist, newest=False)
	workflows = [_format_workflow(w) for w in workflows]
	historical_workflows, newest_workflow = workflows[:-1], workflows[-1]
	historical_messages = [m for w in historical_workflows for m in w] if memory else []
	newest_messages = newest_workflow

	match eval_type:
		case "task_eval":
			input_messages = pruning_func([*historical_messages, *newest_messages])
			message = await task_evaluation(model, input_messages)
			return return_messages([message], "task_eval", "node_research_manager", "call_evaluation")
		case "visual_eval":
			input_messages = pruning_func([*newest_messages])
			message = await visual_evaluation(model, input_messages)
			next = f"node_{specialist}" if not specialist.startswith("node_") else specialist
			return return_messages([message], "visual_eval", next, "call_evaluation")
		case "tool_eval":
			input_messages = pruning_func([*newest_messages])
			message = await tool_evaluation(model, input_messages)
			next = f"node_{specialist}" if not specialist.startswith("node_") else specialist
			return return_messages([message], "tool_eval", next, "call_evaluation")


async def tool_evaluation(model, input_messages):
	system_message = HumanMessage(content=tool_eval_prompt.invoke({}).messages[0].content)

	tags = ["node_evaluation_specialist", "tool_eval"]
	response = await model.ainvoke( [*input_messages, system_message], config={"tags": tags} )
	response.tags = tags
	
	response.tool_calls = []
	response.content = _extract_xml_tags_from_text(response.text, ["reflection", "reward"])
	return response

async def visual_evaluation(model, input_messages):
	system_message = HumanMessage(content=visual_eval_prompt.invoke({}).messages[0].content)

	tags = ["node_evaluation_specialist", "visual_eval"]
	response = await model.ainvoke( [input_messages[0], _multimodal_message(input_messages[-1]), system_message], config={"tags": tags} )
	response.tags = tags

	response.tool_calls = []
	response.content = _extract_xml_tags_from_text(response.text, ["caption", "reflection", "reward"])
	return response



async def task_evaluation(model, input_messages):
	system_message = HumanMessage(content=task_eval_prompt.invoke({}).messages[0].content)
	
	tags = ["node_evaluation_specialist", "task_eval"]
	response = await model.ainvoke( [*input_messages, system_message], config={"tags": tags} )
	response.tags = tags

	response.tool_calls = []
	response.content = _extract_xml_tags_from_text(response.text, ["report", "reward"])
	return response
