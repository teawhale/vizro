"""Dev app to try things out."""

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Dash, html
from vizro.figures.library import kpi_card, kpi_card_reference

df_kpi = pd.DataFrame({"Actual": [100, 200, 700], "Reference": [100, 300, 500], "Category": ["A", "B", "C"]})

# Add single CSS file figures.css or
base = "https://cdn.jsdelivr.net/gh/mckinsey/vizro/vizro-core/src/vizro/static/css/"
vizro_bootstrap = base + "vizro-bootstrap.min.css"

# Add entire assets folder from Vizro
app = Dash(external_stylesheets=[vizro_bootstrap])

app.layout = dbc.Container(
    [
        html.H1(children="Title of Dash App"),
        html.Div(
            children=[
                dbc.Row(
                    [
                        dbc.Col(
                            kpi_card(
                                data_frame=df_kpi,
                                value_column="Actual",
                                value_format="${value:.2f}",
                                icon="shopping_cart",
                                title="KPI Card I",
                            )
                        ),
                        dbc.Col(
                            kpi_card_reference(
                                data_frame=df_kpi,
                                value_column="Actual",
                                reference_column="Reference",
                                icon="payment",
                                title="KPI Card II",
                            )
                        ),
                        dbc.Col(
                            kpi_card_reference(
                                data_frame=df_kpi,
                                value_column="Reference",
                                reference_column="Actual",
                                icon="payment",
                                title="KPI Card III",
                            )
                        ),
                    ]
                ),
            ],
            # TODO: Can we get rid of the requirement to add className="vizro_light"?
            className="vizro_light",
        ),
    ]
)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)
