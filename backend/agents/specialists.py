from pydantic import BaseModel, Field
from typing import Type
from langchain.tools import BaseTool
from tools import sql_list_table_tool, sql_get_schema_tool, sql_query_tool
from tools import python_jupyter_tool, r_jupyter_tool, julia_jupyter_tool
from tools import search_name_tool, search_literature_advanced_tool


class SpecialistInput(BaseModel):
	task: str = Field(..., description="""
The task brief for the specialist. The specialist sees ONLY this brief (plus its own prior tasks when memory=True) - it cannot see the user conversation or other specialists' work. Provide a complete, self-contained brief:
<task_brief>
	<objective>What to produce. State WHAT, not HOW.</objective>
	<inputs>Exact references: absolute file paths with brief schema and row counts, table names, entity ids, and relevant conclusions from earlier tasks.</inputs>
	<deliverable>The expected form of the output.</deliverable>
	<constraints>Scope boundaries; what NOT to do.</constraints>
</task_brief>
""")
	memory: bool = Field(..., description="""If True, the specialist also sees its own previous task transcripts from this conversation. Set True when the new task builds on its earlier outputs (files, queries, variables); False to start clean.""")


class DatabaseSpecialist(BaseTool):
	name: str = "database_specialist"
	description: str = """
	`database_specialist` is a specialized agent for data extraction and preprocessing over the SciSciNet scholarly database. It helps with:
	1. Navigate the schemas of the scholarly database
	2. Identify, extract, clean, and aggregate relevant data segments
	3. Entity name disambiguation (institutions, research fields)
	4. Abstract-level vector search across ALL fields of science - the fallback for literature outside the Science-of-Science corpus
	It does NOT do statistical analysis, modeling, or visualization.
	It returns file paths of extracted datasets in its handoff.
	Invoke this tool to assign a task to `database_specialist`.
	"""
	args_schema: Type[BaseModel] = SpecialistInput
	tools: list[BaseTool] = []
	def _run(self, task: str, memory: bool):
		return {"response": "Connected to DatabaseSpecialist:"}
	
class AnalyticsSpecialist(BaseTool):
	name: str = "analytics_specialist"
	description: str = """
	`analytics_specialist` is a specialized agent for statistical analysis and visualization using Python, R, and Julia sandboxes. It helps with:
	1. Designing and implementing analytical approaches (statistics, modeling, machine learning)
	2. Creating data visualizations and plots
	3. Any other tasks that require coding

	Important notes:
	- It has NO database access: it can only load data files whose absolute paths are given in the task brief
	- Works with data files produced by database_specialist
	- Focuses on analysis strategy and implementation, not data retrieval

	Invoke this tool to assign analytical tasks to `analytics_specialist`.
	"""
	args_schema: Type[BaseModel] = SpecialistInput
	tools: list[BaseTool] = []
	def _run(self, task: str, memory: bool):
		return {"response": "Connected to AnalyticsSpecialist:"}
	
class LiteratureSpecialist(BaseTool):
	name: str = "literature_specialist"
	description: str = """
	`literature_specialist` is a specialized agent for retrieval-augmented review over SciSciCorpus, a curated corpus of Science-of-Science publications (partial coverage). It helps with:
	1. Locating and retrieving relevant papers from the Science of Science literature
	2. Extracting key methodological approaches and findings from papers
	3. Highlighting implications and applications of existing research
	Not for papers outside the SciSci field - use database_specialist's abstract-level vector search for those.
	Empty results may reflect corpus gaps rather than research gaps.
	Invoke this tool to assign a task to `literature_specialist`.
	"""
	args_schema: Type[BaseModel] = SpecialistInput
	tools: list[BaseTool] = []
	def _run(self, task: str, memory: bool):
		return {"response": "Connected to LiteratureSpecialist:"}
	
class EvaluationSpecialist(BaseTool):
	name: str = "evaluation_specialist"
	description: str = "Call this tool when your task is fully complete, right after your <handoff> block. It ends your task: an independent evaluation report is generated for the ResearchManager. You will not receive a reply."
	tools: list[BaseTool] = []
	def _run(self):
		return {"response": "Evaluation Specialist: Evaluating the task."}
	
database_specialist = DatabaseSpecialist(tools=[sql_list_table_tool, sql_get_schema_tool, sql_query_tool, search_name_tool])
analytics_specialist = AnalyticsSpecialist(tools=[python_jupyter_tool, r_jupyter_tool, julia_jupyter_tool])
literature_specialist = LiteratureSpecialist(tools=[search_literature_advanced_tool])
evaluation_specialist = EvaluationSpecialist(tools=[])

__all__ = [database_specialist, analytics_specialist, literature_specialist, evaluation_specialist]