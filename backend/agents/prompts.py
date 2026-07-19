import json, os
from langchain_core.load import load

_prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

def _load_prompt(name: str):
    with open(os.path.join(_prompts_dir, f"{name}.json")) as f:
        return load(json.load(f))

tool_eval_prompt = _load_prompt("sciscigpt-tool-eval")
visual_eval_prompt = _load_prompt("sciscigpt-visual-eval")
task_eval_prompt = _load_prompt("sciscigpt-task-eval")

research_manager_prompt = _load_prompt("sciscigpt_research_manager")

specialist_prompt_dict = {
    "literature_specialist": _load_prompt("sciscigpt_literature_specialist"),
    "database_specialist": _load_prompt("sciscigpt_database_specialist"),
    "analytics_specialist": _load_prompt("sciscigpt_analytics_specialist"),
}