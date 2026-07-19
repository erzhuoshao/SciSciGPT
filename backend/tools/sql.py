# flake8: noqa
import pandas as pd, numpy as np, os, re
pd.set_option('display.float_format', lambda x: '%.2f' % x)

import uuid, json, base64
from tools.display_dataframe import display_dataframe
from functools import lru_cache
from langchain.tools import BaseTool
from typing import Any, Dict, Optional, Sequence, Type, Union
from langchain_community.utilities import SQLDatabase
from pydantic import BaseModel, Field, ConfigDict

from langchain_core.runnables.config import run_in_executor

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import InjectedState
from typing_extensions import Annotated

from func_timeout import func_timeout
from func.gcp import upload_file_to_gcp

bigquery_uri = os.getenv("GOOGLE_BIGQUERY_URI")
workspace = os.getenv("LOCAL_STORAGE_PATH")

class BaseSQLDatabaseTool(BaseModel):
	db_dict: Dict[str, SQLDatabase] = Field(exclude=True)
	model_config = ConfigDict(
		arbitrary_types_allowed=True,
	)


class SQLListTableInput(BaseModel):
	query: str = Field(default="", description="An empty string")
class SQLListTableTool(BaseSQLDatabaseTool, BaseTool):
	name: str = "sql_list_table"
	description: str = """
	Function: List all available tables in the SQL database.
	Input: An empty string.
	Output: The names and brief descriptions of all tables in the database.
	"""
	response_format: str = "content_and_artifact"
	args_schema: Type[BaseModel] = SQLListTableInput

	db_name: str = "SciSciNet_US_V5"
	display_mode: str = "markdown"

	def _run(self, query:str):

		response = {}
		try:
			table_dict = [{
				"TableName": table.name, 
				"TableDescription": table.comment
			} for table in self.db_dict[self.db_name]._metadata.sorted_tables]

			if self.display_mode == "markdown":
				output = pd.DataFrame(table_dict).to_markdown(index=False)
			else:
				output = json.dumps(table_dict, indent=4)

			response['response'] = output

		except Exception as e:
			response['response'] = "{}: {}".format(type(e).__name__, str(e))
		
		return response, response

	async def _arun(self, query:str):
		return await run_in_executor(None, self._run, query)


@lru_cache(maxsize=32)
def cached_get_table_info(db, table_names_tuple):
	if isinstance(table_names_tuple, str):
		table_names_tuple = (table_names_tuple,)
	return db.get_table_info_no_throw(table_names_tuple)

def clear_table_info_cache():
	cached_get_table_info.cache_clear()

def read_sql(query: str, db: SQLDatabase, chunksize: int=1000, timeout: int=120):
	df_list = func_timeout(timeout, pd.read_sql, kwargs={"sql":query, "con":db._engine.connect(), "chunksize":chunksize})
	df = df_list if isinstance(df_list, pd.DataFrame) else pd.concat([i for i in df_list])
	for col in df.columns:
		if df[col].dtype == list:
			df[col] = df[col].apply(lambda x: np.array(x))
	return df

class SQLGetSchemaInput(BaseModel):
	query: str = Field(default="", description="A list of table names separated by commas. For example, `table1, table2, table3`.")
class SQLGetSchemaTool(BaseSQLDatabaseTool, BaseTool):
	name: str = "sql_get_schema"
	description: str = """
	Function: Retrieves detailed schema information and sample rows for specified tables.
	Input: A comma-separated list of table names. If left empty, retrieves information for all available tables.
	Output:
	For each specified table:
	1. Detailed column information (names, data types, descriptions)
	2. Sample rows to illustrate the data structure
	Dependencies:
	1. Use `sql_list_table` to get a list of all available tables.
	"""
	response_format: str = "content_and_artifact"
	args_schema: Type[BaseModel] = SQLGetSchemaInput

	sample_rows: int = 3

	db_name: str = "SciSciNet_US_V5"

	def _run(self, query:str):
		db = self.db_dict[self.db_name]

		response = {}
		try:
			if query == "":
				table_names = db.get_usable_table_names()
			else:
				table_names = [i.strip() for i in query.split(",")]

			# Convert list to tuple for caching
			table_names_tuple = tuple(sorted(table_names))
			# Get table info one by one and combine results

			table_info_list = []
			for table_name in table_names_tuple:
				single_table_info = cached_get_table_info(db, (table_name,))
				table_info_list.append(single_table_info)
			
				df = read_sql(f"SELECT * FROM (SELECT * FROM {table_name} LIMIT 1000) AS t ORDER BY RAND() LIMIT {self.sample_rows}", db)
				#df_string = display_dataframe(df, mode="markdown", display_rows=100, decimal_precision=4)
				#df_string = "\n".join(df_string.split("\n")[:-1])
				df_string = display_dataframe(df, mode="string", display_rows=100, decimal_precision=4)
				table_info_list.append(f"\n/*\n{self.sample_rows} rows from {table_name} table:\n{df_string}\n*/\n")

			response["response"] = "\n".join(table_info_list)
		except Exception as e:
			response["response"] = "{}: {}".format(type(e).__name__, str(e))
		return response, response

	async def _arun(self, query:str):
		return await run_in_executor(None, self.run, query)



from typing import Literal

sql_query_tool_description = """
Function: Executes a SQL query on Google BigQuery.
Output:
1. The header of the result table (top 10 rows). 
2. The file path where the complete result is stored.
Dependencies:
1. Use `sql_get_schema` and `sql_list_table` to retrieve the schema of relevant tables (if necessary).
2. Use `search_name` for accurate name matching if needed (if necessary).

Note: 
1. Ensure your query is well-formed
2. Ensure all tables and columns actually exist in the database

Custom functions:
`SciSciNet_US_V5.TEXT_EMBEDDING` is defined to convert text to embeddings.
`VECTOR_SEARCH` is defined to perform similarity search (Note that the result sub-table is named as `base`).

Example query:
```sql
-- Get papers that are relevant to the search query
SELECT
  vs.base.*, vs.distance
FROM VECTOR_SEARCH(
  TABLE SciSciNet_US_V5.papers,
  "abstract_embedding",
  (SELECT SciSciNet_US_V5.TEXT_EMBEDDING('YOUR SEARCH QUERY')), 
  top_k => NUMBER_OF_RESULTS
) vs
```"""

class SQLQueryInput(BaseModel):
	query: str = Field(..., description="A valid SQL query compatible with Google BigQuery dialect.")
	state: Annotated[dict, InjectedState] = Field(None, description="Agent state")
	# display_mode: Literal["preview", "complete"] = Field(..., description="`preview` will display the first 10 rows. `complete` will display the complete result.")
	# display_rows: int = Field(10, description="The number of rows to display in the preview.")
	
class SQLQueryTool(BaseSQLDatabaseTool, BaseTool):
	name: str = "sql_query"
	description: str = sql_query_tool_description
	response_format: str = "content_and_artifact"
	args_schema: Type[BaseModel] = SQLQueryInput

	db_name: str = "SciSciNet_US_V5"
	session_id: str = "test"

	sendfile: bool = False
	filename: str = None

	chunksize: int = 1000
	timeout: int = 240

	workspace: str = workspace
	display_mode: str = "markdown"
	display_rows_preview: int = 10
	display_rows_complete: int = 200
	demical_precision: int = 4

	def _run(self, query: str, state: dict=None, display_rows: int=10, display_mode: Literal["preview", "complete"]="preview"):
		try:
			# display_rows = self.display_rows_preview if display_mode == "preview" else self.display_rows_complete

			response = {}
			session_id = ((state or {}).get("metadata") or {}).get("session_id", "test")
			safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id)) or "default"
			output_dir = os.path.join(self.workspace, f"session-{safe}")
			os.makedirs(output_dir, exist_ok=True)

			db = self.db_dict[self.db_name]
			df = read_sql(query, db, self.chunksize, self.timeout)
			
			df_string = display_dataframe(
				df, mode=self.display_mode,
				# display_rows=self.display_rows, 
				display_rows=display_rows, 
				decimal_precision=self.demical_precision
			)

			response['response'] = df_string
			
			file_id = str(uuid.uuid4())
			file_name = self.filename if self.filename else f"{file_id}.parquet"
			file_path = f"{output_dir}/{file_name}"

			df.to_parquet(file_path, index=False)

			response["files"] = [{
				"name": file_name,
				"id": file_id,
				"download_link": upload_file_to_gcp(file_path),
				"file_path": file_path,
				"mime_type": "application/parquet",
			}]

			# response["file"] = file_path
			response['note'] = "`response`: header of the SQL query result (may not be complete). `files`: the file of complete SQL query results. Load this file to get the complete result."

		except Exception as e:
			e_str = re.sub(r'\[SQL:\s*.*?\]', '', str(e), flags=re.DOTALL)
			response['response'] = "{}: {}".format(type(e).__name__, e_str)
		return response, response

	async def _arun(self, query:str):
		return await run_in_executor(None, self.run, query)
	

db_name = bigquery_uri.split("/")[-1]
# Initialize tools
db_dict = {
	db_name: SQLDatabase.from_uri(
		database_uri=bigquery_uri, 
		sample_rows_in_table_info=0, 
	)
}

sql_list_table_tool = SQLListTableTool(db_dict=db_dict)
sql_get_schema_tool = SQLGetSchemaTool(db_dict=db_dict)
sql_query_tool = SQLQueryTool(db_dict=db_dict)


