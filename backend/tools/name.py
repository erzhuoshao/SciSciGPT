from typing import Type
from langchain.tools import BaseTool

from pydantic import BaseModel, Field
import pandas as pd
import json

import os

class SearchNameInput(BaseModel):
	column: str = Field(..., description="Specifies the database column to search within. Current valid options only include `field_name` and `institution_name`.")
	value: str = Field(..., description="Defines the name to search for within the specified column.")

class SearchNameTool(BaseTool):
	name: str = "search_name"
	description: str = """
	Function: Searches for and retrieves the closest matches for institution or field names in the database, for name disambiguation and finding standardized names.
	Input: 
	1. column: Specifies which column to search in. Must be either 'field_name' or 'institution_name'.
	2. value: The search term to look for within the specified column.
	Output: A markdown-formatted table of the best-matching rows, including relevant metadata.
	"""
	args_schema: Type[BaseModel] = SearchNameInput

	vectorstore_dict: dict
	type_dict: dict
	

	def _run(self, column: str, value: str, search_filter: str="{}"):
		response = {}
		try:
			search_filter = json.loads(search_filter)
			output = self.vectorstore_dict[column].similarity_search(value, filter=search_filter, k=10)
			output = [result.metadata for result in output]
			output = pd.DataFrame(output)
			response['response'] = output.astype(self.type_dict[column]).to_markdown(floatfmt="")
		except Exception as e:
			response['response'] = "{}: {}".format(type(e).__name__, str(e))
		finally:
			return response
		


type_dict = {
	"institution_name": {
		"institution_id": "Int64",
		"institution_name": "string",
		"grid_id": "string",
		"url": "string",
		"latitude": "double",
		"longitude": "double",
	},
	"field_name": {
		"field_id": "Int64",
		"field_name": "string",
		"field_level": "string",
	}
}
		

# Initialize tools
from langchain_openai import OpenAIEmbeddings

# Same VECTOR_BACKEND switch as tools/literature.py.
if os.getenv("VECTOR_BACKEND", "pinecone").lower() == "chroma":
	from chroma.factory import make_entity_stores
	vectorstore_dict = make_entity_stores()
else:
	from langchain_pinecone import PineconeVectorStore
	vectorstore_dict = {
		namespace: PineconeVectorStore.from_existing_index(
			embedding = OpenAIEmbeddings(model="text-embedding-3-small"),
			namespace = namespace,
			index_name = os.getenv("NAME_SEARCH_INDEX")
		) for namespace in ["field_name", "institution_name"]
	}

search_name_tool = SearchNameTool(vectorstore_dict=vectorstore_dict, type_dict=type_dict)
