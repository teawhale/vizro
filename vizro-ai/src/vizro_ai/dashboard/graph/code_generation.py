from typing import Any, List, Dict
import re

import pandas as pd
from langgraph.graph import END, StateGraph
from vizro_ai.chains._llm_models import _get_llm_model
from vizro_ai.dashboard.nodes.data_summary import DfInfo, df_sum_prompt, _get_df_info
from vizro_ai.dashboard.nodes.imports_builder import ModelSummary, model_sum_prompt, generate_import_statement
from vizro_ai.dashboard.nodes.core_builder.vizro_ai_db import VizroAIDashboard

try:
    from pydantic.v1 import BaseModel, validator
except ImportError:  # pragma: no cov
    from pydantic import BaseModel, validator

# model_default = "gpt-3.5-turbo"
model_default = "gpt-4-turbo"


# def add(existing: Dict, new: Dict[str, Dict[str, str]]):
#     return new

class GraphState(BaseModel):
    """Represents the state of dashboard graph.

    Attributes
        messages : With user question, error messages, reasoning
        dfs : Dataframes
        df_metadata : Cleaned dataframe names and their metadata

    """

    messages: List
    dfs: List[pd.DataFrame]
    # df_metadata: Annotated[Dict[str, Dict[str, Any]], add]
    df_metadata: Dict[str, Dict[str, Any]]

    class Config:
        arbitrary_types_allowed = True

    @validator('dfs')
    def check_dataframes(cls, v):
        if not isinstance(v, list):
            raise ValueError('dfs must be a list')
        for df in v:
            if not isinstance(df, pd.DataFrame):
                raise ValueError('Each element in dfs must be a Pandas DataFrame')
        return v


def store_df_info(state: GraphState):
    """Store information about the dataframes.

    Args:
        state (dict): The current graph state.
    """
    dfs = state.dfs
    messages = state.messages
    df_metadata = state.df_metadata
    current_df_names = []
    for _, df in enumerate(dfs):
        df_schema, df_sample = _get_df_info(df)
        data_sum_chain = df_sum_prompt | _get_llm_model(model=model_default).with_structured_output(
            DfInfo
        )

        df_name = data_sum_chain.invoke(
            {"df_schema": df_schema, "df_sample": df_sample, "messages": messages, "current_df_names": current_df_names}
        )

        print(f"df_name: {df_name}")
        current_df_names.append(df_name)

        cleaned_df_name = df_name.dataset_name.lower()
        cleaned_df_name = re.sub(r'\W+', '_', cleaned_df_name)
        df_id = cleaned_df_name.strip('_')
        print(f"df_id: {df_id}")
        df_metadata[df_id] = {"df_schema": df_schema, "df_sample": df_sample}

    return {"df_metadata": df_metadata}


def compose_imports_code(state: GraphState):
    """Generate code snippet for imports.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation

    """
    messages = state.messages
    model_sum_chain = model_sum_prompt | _get_llm_model(model=model_default).with_structured_output(ModelSummary)

    vizro_model_summary = model_sum_chain.invoke({"messages": messages})

    import_statement = generate_import_statement(vizro_model_summary)

    messages += [
        (
            "assistant",
            import_statement,
        )
    ]
    return {"messages": messages}


def generate_dashboard_code(state: GraphState):
    """Generate a dashboard code snippet.

    Args:
        state (dict): The current graph state
    """
    messages = state.messages
    _, import_statement = messages[-1]
    # dfs = state["dfs"]
    df_metadata = state.df_metadata

    model = _get_llm_model(model=model_default)
    vizro_ai_dashboard = VizroAIDashboard(model)
    dashboard = vizro_ai_dashboard.build_dashboard(messages[0][1], df_metadata)
    dashboard_code_string = dashboard.dict_obj(exclude_unset=True)
    full_code_string = f"\n{import_statement}\ndashboard={dashboard_code_string}\n\nVizro().build(dashboard).run()\n"
    print(f"full_code_string: \n ------- \n{full_code_string}\n ------- \n")

    messages += [
        (
            "assistant",
            full_code_string,
        )
    ]
    return {"messages": messages}


def _create_and_compile_graph():
    graph = StateGraph(GraphState)

    graph.add_node("store_df_info", store_df_info)
    graph.add_node("compose_imports_code", compose_imports_code)
    graph.add_node("generate_dashboard_code", generate_dashboard_code)

    graph.add_edge("store_df_info", "compose_imports_code")
    graph.add_edge("compose_imports_code", "generate_dashboard_code")
    graph.add_edge("generate_dashboard_code", END)

    graph.set_entry_point("store_df_info")

    runnable = graph.compile()

    return runnable
