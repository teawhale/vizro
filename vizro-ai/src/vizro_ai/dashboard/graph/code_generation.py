"""Code generation graph for dashboard generation."""

import logging
import re
from typing import Any, Dict, List

import pandas as pd
from langgraph.graph import END, StateGraph
from vizro.models import Dashboard
from vizro_ai.chains._llm_models import _get_llm_model
from vizro_ai.dashboard.nodes.core_builder.build import DashboardBuilder
from vizro_ai.dashboard.nodes.core_builder.plan import DashboardPlanner, _get_dashboard_plan, _print_dashboard_plan
from vizro_ai.dashboard.nodes.data_summary import DfInfo, _get_df_info, df_sum_prompt
from vizro_ai.dashboard.nodes.imports_builder import ModelSummary, _generate_import_statement, model_sum_prompt

try:
    from pydantic.v1 import BaseModel, validator
except ImportError:  # pragma: no cov
    from pydantic import BaseModel, validator


logger = logging.getLogger(__name__)

model_default = "gpt-3.5-turbo"
# model_default = "gpt-4-turbo"
# set_debug(True)


class GraphState(BaseModel):
    """Represents the state of dashboard graph.

    Attributes
        messages : With user question, error messages, reasoning
        dfs : Dataframes
        df_metadata : Cleaned dataframe names and their metadata
        dashboard_plan : Plan for the dashboard
        dashboard : Vizro dashboard

    """

    messages: List
    dfs: List[pd.DataFrame]
    df_metadata: Dict[str, Dict[str, Any]]
    dashboard_plan: DashboardPlanner = None
    dashboard: Dashboard = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    @validator("dfs")
    def check_dataframes(cls, v):
        """Check if the dataframes are valid."""
        if not isinstance(v, list):
            raise ValueError("dfs must be a list")
        for df in v:
            if not isinstance(df, pd.DataFrame):
                raise ValueError("Each element in dfs must be a Pandas DataFrame")
        return v


def _store_df_info(state: GraphState):
    """Store information about the dataframes.

    Args:
        state (dict): The current graph state.

    """
    logger.info("*** _store_df_info ***")
    dfs = state.dfs
    messages = state.messages
    df_metadata = state.df_metadata
    current_df_names = []
    for _, df in enumerate(dfs):
        df_schema, df_sample = _get_df_info(df)
        data_sum_chain = df_sum_prompt | _get_llm_model(model=model_default).with_structured_output(DfInfo)

        df_name = data_sum_chain.invoke(
            {"df_schema": df_schema, "df_sample": df_sample, "messages": messages, "current_df_names": current_df_names}
        )

        current_df_names.append(df_name)

        cleaned_df_name = df_name.dataset_name.lower()
        cleaned_df_name = re.sub(r"\W+", "_", cleaned_df_name)
        df_id = cleaned_df_name.strip("_")
        logger.info(f"df_name: {df_name} --> df_id: {df_id}")
        df_metadata[df_id] = {"df_schema": df_schema, "df_sample": df_sample}

    return {"df_metadata": df_metadata}


def _compose_imports_code(state: GraphState):
    """Generate code snippet for imports.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation

    """
    logger.info("*** _compose_imports_code ***")
    messages = state.messages
    model_sum_chain = model_sum_prompt | _get_llm_model(model=model_default).with_structured_output(ModelSummary)

    vizro_model_summary = model_sum_chain.invoke({"messages": messages})

    import_statement = _generate_import_statement(vizro_model_summary)

    messages += [
        (
            "assistant",
            import_statement,
        )
    ]
    return {"messages": messages}


def _dashboard_plan(state: GraphState):
    """Generate a dashboard plan.

    Args:
        state (dict): The current graph state

    """
    logger.info("*** _dashboard_plan ***")
    messages = state.messages
    _, query = messages[0]
    df_metadata = state.df_metadata
    dashboard_plan = state.dashboard_plan

    model = _get_llm_model(model=model_default)
    dashboard_plan = _get_dashboard_plan(query=query, model=model, df_metadata=df_metadata)
    _print_dashboard_plan(dashboard_plan)

    return {"dashboard_plan": dashboard_plan}


def _build_dashboard(state: GraphState):
    """Build a dashboard.

    Args:
        state (dict): The current graph state

    """
    logger.info("*** _build_dashboard ***")
    df_metadata = state.df_metadata
    dashboard_plan = state.dashboard_plan

    model = _get_llm_model(model=model_default)
    dashboard = DashboardBuilder(
        model=model,
        df_metadata=df_metadata,
        dashboard_plan=dashboard_plan,
    ).dashboard

    return {"dashboard": dashboard}


def _generate_dashboard_code(state: GraphState):
    """Generate a dashboard code snippet.

    Args:
        state (dict): The current graph state

    """
    logger.info("*** _generate_dashboard_code ***")
    messages = state.messages
    _, import_statement = messages[-1]
    dashboard = state.dashboard

    dashboard_code_string = dashboard.dict_obj(exclude_unset=True)
    full_code_string = f"\n{import_statement}\ndashboard={dashboard_code_string}\n\nVizro().build(dashboard).run()\n"
    logger.info(f"full_code_string: \n ------- \n{full_code_string}\n ------- \n")

    messages += [
        (
            "assistant",
            full_code_string,
        )
    ]
    return {"messages": messages}


def _create_and_compile_graph():
    graph = StateGraph(GraphState)

    graph.add_node("_store_df_info", _store_df_info)
    graph.add_node("_compose_imports_code", _compose_imports_code)
    graph.add_node("_dashboard_plan", _dashboard_plan)
    graph.add_node("_build_dashboard", _build_dashboard)
    graph.add_node("_generate_dashboard_code", _generate_dashboard_code)

    graph.add_edge("_store_df_info", "_compose_imports_code")
    graph.add_edge("_compose_imports_code", "_dashboard_plan")
    graph.add_edge("_dashboard_plan", "_build_dashboard")
    graph.add_edge("_build_dashboard", "_generate_dashboard_code")
    graph.add_edge("_generate_dashboard_code", END)

    graph.set_entry_point("_store_df_info")

    runnable = graph.compile()

    return runnable


if __name__ == "__main__":
    test_state = {
        "messages": [
            (
                "user",
                "\nI need a page with a table showing the population per continent \n"
                "I also want a page with two \ncards on it. One should be a card saying: "
                "`This was the jolly data dashboard, it was created in Vizro which is amazing` \n, "
                "and the second card should link to `https://vizro.readthedocs.io/`. The title of "
                "the dashboard should be: `My wonderful \njolly dashboard showing a lot of info`.\n"
                "The layout of this page should use `grid=[[0,1]]`",
            ),
            (
                "assistant",
                "from vizro import Vizro\nfrom vizro.models import AgGrid, Card, Dashboard, Page\nfrom "
                "vizro.tables import dash_ag_grid\nimport pandas as pd\n",
            ),
        ],
        "dfs": [
            pd.DataFrame(),
        ],
        "df_metadata": {
            "globaldemographics": {
                "df_schema": {
                    "country": "object",
                    "continent": "object",
                    "year": "int64",
                    "lifeExp": "float64",
                    "pop": "int64",
                    "gdpPercap": "float64",
                    "iso_alpha": "object",
                    "iso_num": "int64",
                },
                "df_sample": "|      | country   | continent   |   year |   lifeExp |      pop |   "
                "gdpPercap | iso_alpha   |   iso_num |\n|-----:|:----------|:------------|-------:"
                "|----------:|---------:|------------:|:------------|----------:|\n|  215 | "
                "Burundi   | Africa      |   2007 |    49.58  |  8390505 |     430.071 | BDI"
                "         |       108 |\n| 1545 | Togo      | Africa      |   1997 |    58.39  |"
                "  4320890 |     982.287 | TGO         |       768 |\n|  772 | Italy     | Europe"
                "      |   1972 |    72.19  | 54365564 |   12269.3   | ITA         |       380 |\n|"
                " 1322 | Senegal   | Africa      |   1962 |    41.454 |  3430243 |    1654.99  | SEN"
                "         |       686 |\n|  732 | Iraq      | Asia        |   1952 |    45.32  |  5441766"
                " |    4129.77  | IRQ         |       368 |",
            },
        },
    }
    sample_state = GraphState(**test_state)
    message = _generate_dashboard_code(sample_state)
    print(message)  # noqa: T201
