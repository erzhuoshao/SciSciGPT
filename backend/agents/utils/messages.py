from langchain_core.messages import HumanMessage, AIMessage, AnyMessage, ToolMessage
from copy import deepcopy
import re



def _extract_xml_tag_from_text(text: str, tag: str):
	# Extract the text between the tags
	# If the tag is not found, return an empty string
	match = re.search(fr'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
	if match:
		return match.group(1).strip() if match.group(1) else ""
	else:
		return ""


def _extract_xml_tags_from_text(text: str, tags: list[str]) -> str:
	xml_dict = { tag: _extract_xml_tag_from_text(text, tag) for tag in tags }
	extracted_xml = "\n".join([f"<{tag}>{xml_dict[tag]}</{tag}>" for tag in tags if xml_dict[tag]])
	return extracted_xml.strip() if extracted_xml else ""



def _remove_xml_tags_from_messages(messages: list[AnyMessage], tags: list[str]):
	messages = deepcopy(messages)
	
	for tag in tags:
		pattern = re.compile(fr'<{tag}>(.*?)</{tag}>', re.DOTALL)
		for message in messages:
			if isinstance(message, AIMessage):
				message.content = pattern.sub("", message.text).strip()

	messages = [_format_message(message) for message in messages]
	return messages


def _extract_task_from_message(message: AIMessage | list[AnyMessage]):
    current = getattr(message, "metadata", {}).get("current", "")
    
    if isinstance(message, AIMessage) and "research_manager" in current:
        if not message.tool_calls or len(message.tool_calls) == 0:
            return None
        else:
            specialist = message.tool_calls[0]["name"]
            task = message.tool_calls[0]["args"].get("task", "")
            memory = message.tool_calls[0]["args"].get("memory", None)
            return { "specialist": specialist, "task": task, "memory": memory }

    elif isinstance(message, list):
        for m in message[::-1]:
            task = _extract_task_from_message(m)
            if task:
                return task
        return None

    else:
        return None


def _extract_workflows_from_messages(messages: list[AnyMessage], specialist: str, newest: bool = False) -> list[list[AnyMessage]]:
	workflows = []
	for start in range(len(messages)):
		metadata = getattr(messages[start], "metadata", {})
		task = _extract_task_from_message(messages[start])

		if ("research_manager" in metadata.get("current", "")) and task and (task.get("specialist", "") in specialist):
			workflow = []

			for i in range(start, len(messages)):
				metadata = getattr(messages[i], "metadata", {})
				workflow.append(messages[i])

				if metadata.get("current", None) == "task_eval":
					break

			workflows.append(workflow)

	if newest:
		return workflows[-1] if workflows else []
	else:
		return workflows


def _filter_rm_visible_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
	"""ResearchManager context: user dialogue, its own turns, delegation
	acknowledgements, each task's final handoff message, and task evaluation
	reports. Specialists' intermediate work and raw tool outputs stay out."""
	visible = []
	for message in messages:
		metadata = getattr(message, "metadata", None) or {}
		name = metadata.get("name") or ""
		current = metadata.get("current") or ""
		next = metadata.get("next") or ""

		if name == "call_specialist" and not next.startswith("node_evaluation_specialist"):
			continue
		if name == "call_toolset":
			continue
		if name == "call_evaluation" and current != "task_eval":
			continue
		visible.append(message)
	return visible


def _format_workflow(workflow: list[AnyMessage]) -> list[AnyMessage]:
	task = _extract_task_from_message(workflow)
	messages = [HumanMessage(content=task["task"])]
	for message in workflow:
		metadata = getattr(message, "metadata", {})
		if ("research_manager" in metadata.get("current", "")) and ("specialistset" in metadata.get("name", "")):
			continue
		messages.append(message)
	return messages



from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.load import dumps

def return_messages(messages: list[AnyMessage], current: str, next: str, name: str):
	for message in messages:
		message.metadata = { "current": current, "next": next, "name": name }
		
	messages = [_format_message(message) for message in messages]
	state = { "messages": messages, "current": current, "next": next, "name": name }

	dispatch_custom_event(name, dumps(state))
	return state

def _format_message(message: AnyMessage):
	content = message.content
	if isinstance(content, str):
		content = [{"text": content, "type": "text"}]

	if ("text" not in content[0]) or (content[0]["text"].strip() == ""):
		content = [{"text": "EMPTY MESSAGE", "type": "text"}] + content

	message.content = content
	return message