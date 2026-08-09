from typing import Optional, Type, Literal, Callable
from langchain.tools import BaseTool
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel, Field
from typing import Annotated
from langgraph.prebuilt import InjectedState
import pandas as pd
import re, os
from langchain_core.prompts import ChatPromptTemplate
import json as _json
from langchain_core.load import load as _load_lc

def _load_prompt(name: str):
    _dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    with open(os.path.join(_dir, f"{name}.json")) as f:
        return _load_lc(_json.load(f))

HyDE_pre_retrieval_xml = _load_prompt("sciscigpt_literature_specialist_hyde_pre")
HyDE_post_retrieval_xml = _load_prompt("sciscigpt_literature_specialist_hyde_post")

sciscicorpus_index = os.getenv("SCISCICORPUS_INDEX")
sciscicorpus_namespace = os.getenv("SCISCICORPUS_NAMESPACE")
openai_api_key = os.getenv("OPENAI_API_KEY")

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

def __dict_to_bibtex__(entry):
	entry_2 = {}
	for k, v in entry.items():
		if type(v) == list:
			v = ', '.join(v)
		entry_2[k] = str(v)

	db = BibDatabase()
	db.entries = [entry_2]
	writer = BibTexWriter()
	writer.indent = '\t'
	writer.order_entries_by = None
	return writer.write(db)


from langchain_core.output_parsers import JsonOutputParser, XMLOutputParser

def pre_retrieval_processing(llm, query):
    parser = XMLOutputParser()
    PreRetrievalChain = HyDE_pre_retrieval_xml | llm
    hypo_y = PreRetrievalChain.invoke({
        "query": query, 
        "format_instructions": parser.get_format_instructions()
    }).text()

    hypo_y = re.findall(r'<section>(.*?)</section>', hypo_y, re.DOTALL)
    hypo_y = [i.strip() for i in hypo_y]
    return hypo_y

def post_retrieval_processing_xml(llm, query, search_results):
	"""Process search results into XML format literature review"""

	parser = XMLOutputParser()
	PostRetrievalChain = HyDE_post_retrieval_xml | llm
	response = PostRetrievalChain.invoke({
		"search_results": search_results,
		"query": query,
		"format_instructions": parser.get_format_instructions()
	}).text()
	
	references_match = re.search(r'<references>(.*?)</references>', response, re.DOTALL)
	summary_match = re.search(r'<summary>(.*?)</summary>', response, re.DOTALL)
	
	if not references_match or not summary_match:
		raise ValueError("Invalid XML format in response")
		
	references = references_match.group(1).strip()
	summary = summary_match.group(1).strip()
	
	# Format output with references as markdown links where possible
	thinking = re.search(r'<thinking>(.*?)</thinking>', response, re.DOTALL)
	thinking = thinking.group(1).strip() if thinking else ""
	thinking = f"<thinking>\n\n{thinking}\n\n</thinking>"

	formatted_refs = []
	for ref_match in re.finditer(r'<reference>(.*?)</reference>', references, re.DOTALL):
		ref = ref_match.group(1)
		id_match = re.search(r'<id>(.*?)</id>', ref)
		ref_text_match = re.search(r'<ref>(.*?)</ref>', ref) 
		url_match = re.search(r'<url>(.*?)</url>', ref)
		
		if id_match and ref_text_match:
			ref_id = id_match.group(1).strip().replace('[', '').replace(']', '')
			ref_text = ref_text_match.group(1).strip()
			ref_url = url_match.group(1).strip() if url_match else ""
			
			if ref_url:
				formatted_refs.append(f"{ref_id}. [{ref_text}]({ref_url})")
			else:
				formatted_refs.append(f"{ref_id}. {ref_text}")

	summary = [i.strip() for i in summary.split("\n") if i.strip()]
	# response = "\n\n".join(summary) + "\n\nReferences:\n" + "\n".join(formatted_refs)
	response = "\n\n".join([thinking, *summary, "**References**", *formatted_refs])
	return response



def __format_output_df_as_prompt__(df):
	prompt = []
	for index, row in df.iterrows():
		row = row.to_dict()
		text = row.pop('text')
		prompt.append({
			"text": text, 
			"bibtex": __dict_to_bibtex__(row)
		})
	return prompt

def __search_and_format__(
		PVS, search_keywords, k, 
		section_category=None, min_year=None, max_year=None, url=None, paper_title=None, authors=None, 
		section_id: int=None, venue=None
	):
	filter_conditions = []
	if section_category and section_category != "All":
		filter_conditions.append({"section_category": section_category})
	if min_year:
		filter_conditions.append({"year": {"$gte": int(min_year)}})
	if max_year:
		filter_conditions.append({"year": {"$lte": int(max_year)}})
	if url:
		filter_conditions.append({"url": url})
	if section_id:
		# the corpus stores section_id as a number
		filter_conditions.append({"section_id": float(section_id)})
	if paper_title:
		filter_conditions.append({"paper_title": paper_title})
	if venue:
		# the corpus has no `venue` key: journal articles carry `journaltitle`
		# (and `shortjournal`), books/reports carry `publisher`
		filter_conditions.append({"$or": [
			{"journaltitle": venue}, {"shortjournal": venue}, {"publisher": venue}]})
	filter_query = {"$and": filter_conditions} if filter_conditions else None

	if type(search_keywords) == str:
		search_keywords = [search_keywords]

	# Author matching happens post-retrieval (tolerant), so fetch more first
	k_fetch = k * 3 if authors else k

	df = []
	for search_keyword in search_keywords:
		output = PVS.similarity_search(search_keyword, filter=filter_query, k=k_fetch, namespace=sciscicorpus_namespace)
		df_temp = pd.DataFrame([i.metadata | {'text': i.page_content} for i in output])
		# df_temp.authors = df_temp.authors.apply(lambda x: ', '.join(x[:-1]) + ', and ' + x[-1] if len(x) > 1 else x[0])
		df.append(df_temp)
	df = pd.concat(df, ignore_index=True)

	if authors and df.shape[0] > 0 and "author" in df.columns:
		# Tolerant author filter: every token of a requested name must appear in
		# the chunk's author string (case-insensitive), so partial names like
		# "James Evans" match the stored "James A. Evans".
		def _author_match(author_string):
			s = str(author_string).lower()
			return any(all(tok in s for tok in a.lower().split()) for a in authors)
		df = df[df["author"].apply(_author_match)]
	
	if df.shape[0] > 0:
		df = df.sort_values(['url', 'section_id'])
		df = df.groupby("url").agg({
			"text": lambda x: "\n".join(x),
			"section_id": lambda x: ", ".join([str(int(i)) for i in x])
		} | {k: "first" for k in df.columns if k not in ["text", "section_id"]}).\
			reset_index(drop=True)
		formatted_prompt = __format_output_df_as_prompt__(df)
	else:
		formatted_prompt = "No search results found."
	return formatted_prompt


class SearchConstraints(BaseModel):
	section_category: Literal[
		"All", "Abstract", "Introduction", "Related Works", 
		"Methodology", "Results", "Discussion", "Conclusion", 
		"Appendix", "Acknowledgement"
		] = Field(..., description="Filter results to only of a specific section (`All` for all sections)")
	min_year: Optional[int] = Field(None, 
		description="Filter results to only include papers published after a specific year (YYYY)")
	max_year: Optional[int] = Field(None, 
		description="Filter results to only include papers published before a specific year (YYYY)")
	url: Optional[str] = Field(None, 
		description="Filter results to only include sections from a specific URL")
	paper_title: Optional[str] = Field(None, 
		description="Filter results to only include sections from a specific paper title")
	authors: Optional[list[str]] = Field(None,
		description="Filter results to only include papers written by any of these authors (partial names are matched tolerantly)")
	section_id: Optional[int] = Field(None,
		description="Filter results to only include a specific numeric section ID from papers")
	venue: Optional[str] = Field(None,
		description="Filter results to only include papers published in a specific journal (exact journal name, e.g. `Nature`) or book publisher")

ConstraintTemplate = ChatPromptTemplate([
	("system", """You are an AI assistant specializing in creating search constraints for a literature search."""),
	("human", """Create the search constraints for the following query:
	Query: {query}

	Your output must strictly follow the following XML format without any additional text or comments.
	{format_instructions}
	""")
])

def __create_search_constraints__(llm, query):
	parser = JsonOutputParser(pydantic_object=SearchConstraints)
	SearchConstraintsChain = ConstraintTemplate | llm | parser
	search_constraints = SearchConstraintsChain.invoke({
		"query": query,
		"format_instructions": parser.get_format_instructions()
	})
	return search_constraints


query_description = """The assigned requirements to the tool. Needs to include if needed: 
	1. A detailed requirements of the search query, including the research fields, topics, and questions.
	2. The expected span of papers need to be included in the results. Or the specific types of content that are required.
	3. The instructions for how to summarize the search results, including the expected direction, focus, or specific content or details.
	4. The expected format of the output, including the expected structure, content, style, or reference format."""


class SearchLiteratureAdvancedInput(BaseModel):
	query: str = Field(..., description=query_description)
	k: int = Field(10, 
		description="The number of search results before summarization. Larger k means more search results.")
	state: Annotated[dict, InjectedState] = Field(None, description="Agent state")

class SearchLiteratureAdvancedTool(BaseTool):
	name: str = "search_literature"
	description: str = """
	Function: Performs an advanced semantic search across Science of Science literature to find relevant papers and sections.
	Output: A comprehensive literature review with:
	- Relevant paper sections and quotes
	- Full citations with author names
	- DOI links when available
	- Contextual summary connecting the results to the query
	Note: This tool specializes in Science of Science literature only.
	"""
	args_schema: Type[BaseModel] = SearchLiteratureAdvancedInput
	vs: VectorStore
	load_llm: Callable

	def _run(
		self, query: str, k: int, state: Annotated[dict, InjectedState], **kwargs
		# section: str = None, title: str = None, authors: list = None, 
		# section_id: int = None, venue: str = None
	):
		llm = self.load_llm(state["metadata"], disable_streaming=True)

		response = {}
		try:
			# hypo_ys = [ query ]
			hypo_ys = pre_retrieval_processing(llm, query)

			search_constraints = __create_search_constraints__(llm, query)

			raw_results = __search_and_format__(
				self.vs, 
				hypo_ys, 
				k, **search_constraints
			)

			if raw_results == "No search results found.":
				response['response'] = raw_results
			else:
				response['response'] = post_retrieval_processing_xml(
					llm, query, raw_results)
				# response['response'] = raw_results
				# response['bibtex'] = [i['bibtex'] for i in raw_results]

		except Exception as e:
			error_msg = "{}: {}".format(type(e).__name__, str(e))
			response['response'] = error_msg
		finally:
			return response


from langchain_openai import OpenAIEmbeddings
from llms import load_llm

# Vector store backend switch. "pinecone" (default) is the original behavior;
# "chroma" serves the same corpus from the local store built by
# backend/chroma/build_index.py. Everything downstream consumes the
# VectorStore interface and is unaffected.
if os.getenv("VECTOR_BACKEND", "pinecone").lower() == "chroma":
	from chroma.factory import make_corpus_store
	vs = make_corpus_store(openai_api_key=openai_api_key)
else:
	from langchain_pinecone import PineconeVectorStore
	vs = PineconeVectorStore.from_existing_index(
		embedding = OpenAIEmbeddings(model="text-embedding-3-large", api_key=openai_api_key),
		index_name = sciscicorpus_index,
		namespace = sciscicorpus_namespace,
	)

search_literature_advanced_tool = SearchLiteratureAdvancedTool(vs=vs, load_llm=load_llm)