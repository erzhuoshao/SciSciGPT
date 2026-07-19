from langchain.tools import BaseTool
import re, os, json, uuid, base64

from pydantic import BaseModel, Field
from typing import Type
from typing_extensions import Annotated

from func.jupyter import JupyterSandbox
from func.image import upload_image

from langgraph.prebuilt import InjectedState

working_dir = os.getenv("LOCAL_STORAGE_PATH")

def _parse_jupyter_results(results: list[dict], output_dir: str = None) -> dict:
	text_responses = [r for r in results if r['type'] == 'text']
	image_responses = [r for r in results if r['type'] == 'image_url']

	response = {}
	response["response"] = "".join([r["text"] for r in text_responses])

	if len(image_responses) > 0:
		output_dir = output_dir or working_dir
		os.makedirs(output_dir, exist_ok=True)
		response["images"] = []
		for i in image_responses:
			id = str(uuid.uuid4())
			name = f"{output_dir}/{id}.png"

			with open(name, "wb") as f:
				f.write(base64.b64decode(i["image_url"]["url"].split(",")[1]))
			download_link = upload_image(name)
			
			response["images"].append(
				{ "name": name, "id": id, "mime_type": "image/png", "download_link": download_link })
	return response



class RJupyterInput(BaseModel):
	query: str = Field(..., description="R code snippet to run")
	state: Annotated[dict, InjectedState] = Field(None, description="Agent state")

class RJupyterTool(BaseTool):
	name: str = "r"
	description: str = """Execute R code in a persistent Jupyter environment. Input: Any valid R code snippet to run. Output: Standard output and error messages. Note: you need to call `print(p)` to render the figure."""
	args_schema: Type[BaseModel] = RJupyterInput

	sandbox: JupyterSandbox = None
	timeout: int = 120  # seconds

	def _run(self, query, state = None) -> str:
		try:
			session_id = state["metadata"]["session_id"] if state else "test"
		
			cell_id = uuid.uuid4()
			results = self.sandbox.execute_code(f"%%R\n\n{query}", session_id=session_id, cell_id=cell_id, timeout=self.timeout)
			results = [r for r in results if r["session_id"] == session_id and r["cell_id"] == cell_id]

			response = _parse_jupyter_results(results, self.sandbox.session_dir(session_id))
		except Exception as e:
			response = {"response": "{}: {}".format(type(e).__name__, str(e))}
		return response



class PythonJupyterInput(BaseModel):
	query: str = Field(..., description="Python code snippet to run")
	state: Annotated[dict, InjectedState] = Field(None, description="Agent state")

class PythonJupyterTool(BaseTool):
	name: str = "python"
	description: str = """Execute Python code in a persistent Jupyter environment. Input: Any valid Python code snippet to run. Output: Standard output, error messages, and output images. Always prioritize to use matplotlib or seaborn to plot the figure. Note: Don't save output images to disk. Output images will be rendered automatically. A publication figure style (Okabe-Ito palette, clean axes) is preloaded: build figures with `import sciscigpt_style as style; fig, ax = style.figure()` and use `style.COLORS`; design rules are in FIGURE_STANDARDS.md next to the module."""
	
	args_schema: Type[BaseModel] = PythonJupyterInput

	sandbox: JupyterSandbox = None

	timeout: int = 120  # seconds

	def _run(self, query, state = None) -> str:
		try:
			session_id = state["metadata"]["session_id"] if state else "test"
			
			cell_id = uuid.uuid4()
			results = self.sandbox.execute_code(query, session_id=session_id, cell_id=cell_id, timeout=self.timeout)
			results = [r for r in results if r["session_id"] == session_id and r["cell_id"] == cell_id]
			response = _parse_jupyter_results(results, self.sandbox.session_dir(session_id))
		except Exception as e:
			response = {"response": "{}: {}".format(type(e).__name__, str(e))}
		return response



class JuliaJupyterInput(BaseModel):
	query: str = Field(..., description="Julia code snippet to run")
	state: Annotated[dict, InjectedState] = Field(None, description="Agent state")

class JuliaJupyterTool(BaseTool):
	name: str = "julia"
	description: str = """Execute Julia code in a persistent Jupyter environment. Input: Any valid Julia code snippet to run. Output: Standard output and error messages. Note: you need to call `display(p)` to render the figure."""
	args_schema: Type[BaseModel] = JuliaJupyterInput

	sandbox: JupyterSandbox = None
	timeout: int = 120  # seconds

	def _run(self, query, state = None) -> str:
		try:
			session_id = state["metadata"]["session_id"] if state else "test"
		
			cell_id = uuid.uuid4()
			results = self.sandbox.execute_code(
				f"%%julia\n\n{query}", session_id=session_id, cell_id=cell_id, timeout=self.timeout)
			print(results)
			results = [r for r in results if r["session_id"] == session_id and r["cell_id"] == cell_id]
			response = _parse_jupyter_results(results, self.sandbox.session_dir(session_id))
			print(response)
		except Exception as e:
			response = {"response": "{}: {}".format(type(e).__name__, str(e))}
		return response


# from func.env import python_env_setup, python_env_setup_string
# python_env_setup() # Setup the python environment in system level
jupyter_sandbox = JupyterSandbox(working_dir=working_dir)
python_jupyter_tool = PythonJupyterTool(sandbox=jupyter_sandbox)
r_jupyter_tool = RJupyterTool(sandbox=jupyter_sandbox)
julia_jupyter_tool = JuliaJupyterTool(sandbox=jupyter_sandbox)


if __name__ == "__main__":
	python_test_code = """
	import matplotlib.pyplot as plt
	import numpy as np

	# Generate sample data since x and y are not defined
	x = np.random.rand(50) * 5 + 1  # Weight data (1-6 range)
	y = -5 * x + 35 + np.random.randn(50) * 2  # MPG data with some noise

	plt.scatter(x, y)
	plt.title("Scatter Plot of Weight vs MPG")
	plt.xlabel("Weight")
	plt.ylabel("MPG")
	plt.show()
	"""

	r_test_code = """
	library(ggplot2)
	ggplot(mtcars, aes(x = wt, y = mpg)) + geom_point() + ggtitle("Scatter Plot of Weight vs MPG") + xlab("Weight") + ylab("MPG")
	"""

	julia_test_code = """
	using Plots, Random, Distributions, Colors, StatsPlots
	x = randn(100)
	y = 2x .+ randn(100) * 0.5
	p1 = scatter(x, y, title="Sample Scatter Plot", xlabel="X values", ylabel="Y values", markersize=4, markercolor=:blue, legend=false)
	p2 = histogram(x, title="Sample Histogram", xlabel="X values", ylabel="Frequency", bins=20, color=:green, legend=false)
	p3 = boxplot(x, title="Sample Boxplot", xlabel="X values", ylabel="Values", color=:red, legend=false)
	plot(p1, p2, p3, layout=(3,1), size=(800,600))
	display(plot(p1, p2, p3, layout=(3,1), size=(800,600)))
	"""

	print("########################## Testing Python Jupyter Tool ##########################")
	result = python_jupyter_tool.invoke(python_test_code)
	print(result)

	print("########################## Testing R Jupyter Tool ##########################")
	result = r_jupyter_tool.invoke(r_test_code)
	print(result)

	print("########################## Testing Julia Jupyter Tool ##########################")
	result = julia_jupyter_tool.invoke(julia_test_code)
	print(result)
