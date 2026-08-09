"""Test cases shared by the reference dumper and the parity checker.

Kept dependency-free so it can be imported from both the production conda env
and the local venv.
"""

from __future__ import annotations

REFERENCE_FILE = "reference.json"


def build_filter(section_category=None, min_year=None, max_year=None, url=None,
                 section_id=None, paper_title=None, venue=None, authors=None):
	"""Mirror of the filter construction in literature.py:124-142.

	Kept structurally identical -- including the `{"$and": [<one condition>]}`
	shape that a single constraint produces -- so the parity test exercises the
	filters the tool really emits.
	"""
	conditions = []
	if section_category and section_category != "All":
		conditions.append({"section_category": section_category})
	if min_year:
		conditions.append({"year": {"$gte": int(min_year)}})
	if max_year:
		conditions.append({"year": {"$lte": int(max_year)}})
	if url:
		conditions.append({"url": url})
	if section_id:
		conditions.append({"section_id": float(section_id)})
	if paper_title:
		conditions.append({"paper_title": paper_title})
	if venue:
		conditions.append({"$or": [
			{"journaltitle": venue}, {"shortjournal": venue}, {"publisher": venue}]})
	return {"$and": conditions} if conditions else None


# (label, query, build_filter kwargs)
CORPUS_CASES = [
	("no filter", "how does team size affect scientific innovation", {}),
	("section_category", "measuring scientific impact", {"section_category": "Methodology"}),
	("single condition -> $and unwrap", "citation dynamics", {"min_year": 2015}),
	("year range (two conditions)", "science of science funding", {"min_year": 2010, "max_year": 2020}),
	("venue $or across three fields", "innovation and disruption", {"venue": "Nature"}),
	("category + year range", "peer review bias", {"section_category": "Results", "min_year": 2012, "max_year": 2022}),
	("section_id float coercion", "introduction to bibliometrics", {"section_id": 1}),
	("abstract only", "gender disparities in science", {"section_category": "Abstract"}),
	("narrow year window", "replication crisis", {"min_year": 2018, "max_year": 2019}),
	("no match expected", "quantum chromodynamics lattice gauge", {"min_year": 2200}),
]

# (collection/namespace, query) -- search_name always passes filter == {}
ENTITY_CASES = [
	("institution_name", "Northwestern University"),
	("institution_name", "MIT"),
	("institution_name", "Tsinghua"),
	("institution_name", "Max Planck"),
	("field_name", "computer science"),
	("field_name", "sociology"),
	("field_name", "economics"),
]

# name.py:44-58
TYPE_DICT = {
	"institution_name": {
		"institution_id": "Int64", "institution_name": "string", "grid_id": "string",
		"url": "string", "latitude": "double", "longitude": "double",
	},
	"field_name": {"field_id": "Int64", "field_name": "string", "field_level": "string"},
}
