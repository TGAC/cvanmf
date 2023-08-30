"""
# Enterosignature Transformer
Transform GTDB taxonomic abundance tables to Enterosignature weights
"""

from typing import Collection, List, Tuple, Union
from datetime import date
import io
import zipfile as zf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from entero_process import (EnteroException, validate_table, match_genera, 
                            nmf_transform, model_fit)
import text

# Remove the big top margin to gain more space
# st.set_page_config(layout="wide")
hide_streamlit_style = """
<style>
    #root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 0rem;}
</style>

"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Constants for resource locations etc
ES_W_MATRIX: str = "data/ES5_W.tsv"
PLOTLY_WIDTH: int = 650

# STREAMLIT SPECIFIC FUNCTIONS
@st.cache_data
def _zip_items(items: Collection[Tuple[str, str]]
               ) -> io.BytesIO:
    """Create an in-memory zip file from a collection of objects, so it can be
    offered to a user for download.
    Using suggestions from https://stackoverflow.com/questions/2463770/
    # python-in-memory-zip-library."""
    zbuffer: io.BytesIO = io.BytesIO()
    with zf.ZipFile(zbuffer, "a", zf.ZIP_DEFLATED, False) as z:
        for name, contents in items:
            z.writestr(name, contents)
        # Always add the readme
        z.write("data/README.txt", "README.txt")
    return zbuffer

@st.cache_data
def _plot_heatmap(es: pd.DataFrame) -> go.Figure:
    es_t: pd.DataFrame = es.T
    p_hmap: go.Figure = go.Figure(
        go.Heatmap(
            z = es_t.values,
            x = es_t.columns,
            y = es_t.index
        )
    ).update_layout(width=PLOTLY_WIDTH)
    return p_hmap

@st.cache_data
def _plot_hist(model_fit: pd.DataFrame) -> go.Figure:
    return px.histogram(model_fit, x="model_fit"
                        ).update_layout(width=PLOTLY_WIDTH)

# TODO(apduncan): Caching producing partly empty logs on reruns, might
# be confusing for users

class Logger():
    """Write log to screen as it occurs, but also collect so logs can be 
    written to a file in the results zip."""

    def __init__(self) -> None:
        self.__loglines: List[str] = []
        self.log(f"Date: {date.today()}", to_screen=False)

    def log(self, message: str, to_screen: bool = True) -> None:
        self.__loglines.append(message)
        if to_screen:
            st.write(message)

    def to_file(self) -> str:
        """Concatenate all messages to a single string for writing to 
        file."""
        return "\n".join(self.__loglines)

es_log: Logger = Logger()

# WRAPPER FUNCTIONS
# Wrap some long running functions, so we can apply the streamlit decorators
# without having to apply them to the commandline version of those same
# functions
# TODO(apduncan): Improve caching - hashing a lot of big files
@st.cache_resource
def _get_es_w(file: str) -> pd.DataFrame:
    return pd.read_csv(file, index_col=0, sep="\t") 

@st.cache_data
def _transform_match(abd_tbl: pd.DataFrame
                     ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Sanity check this abundance table
    abd_tbl = validate_table(abd_tbl, logger=es_log.log)

    # Attempt to match the genera
    es_w: pd.DataFrame = _get_es_w(ES_W_MATRIX)
    new_abd, new_w, mapping  = match_genera(
        es_w,
        abd_tbl,
        logger = es_log.log
    )
    return new_abd, new_w, mapping

@st.cache_data
def _transform_transform(new_abd: pd.DataFrame, 
                         new_w: pd.DataFrame) -> pd.DataFrame:
    return nmf_transform(new_abd, new_w, es_log.log)

@st.cache_data
def _transform_model_fit(new_w: pd.DataFrame,
                         es: pd.DataFrame,
                         new_abd: pd.DataFrame) -> pd.DataFrame:
    return model_fit(new_w, es.T, new_abd, es_log.log)

# APP CONTENT
# The app is quite long, so want to try and section it up so people don't 
# miss that they have to scroll for results etc
if "uploaded" not in st.session_state:
    st.session_state.uploaded = False

st.title(text.TITLE)

abd_file = st.file_uploader(
    label = text.UPLOAD_LABEL,
    help = text.UPLOAD_TOOLTIP
)
uploaded = abd_file is not None

expander_upload = st.expander(text.EXPANDER_UPLOAD, expanded=not uploaded)
expander_log = st.expander(text.EXPANDER_LOG, expanded=uploaded)
expander_results = st.expander(text.EXPANDER_RESULTS, expanded=uploaded)

with expander_upload:
    st.markdown(text.SUMMARY)
    st.markdown(text.INPUT_FORMAT)
    st.markdown(text.CAVEATS)


if abd_file is not None:
    try:
        # Attempt to transform the data and return Enterosignatures
        # Any step which fails due to some problem with the data should
        # raise an EnteroException
        abd_tbl = pd.read_csv(abd_file, sep="\t", index_col=0)
        with expander_upload:
            with expander_log:
                # Sanity check this abundance table
                abd_tbl = validate_table(abd_tbl, logger=es_log.log)

                # Attempt to match the genera
                new_abd, new_w, mapping  = _transform_match(abd_tbl)

        # Data has been transformed
        # TODO(apduncan): Allow custom mapping files to be provided
        # TODO(apduncan): UI for fixing mappings

        # Apply NMF with the new data - simple stuff now
        es: pd.DataFrame = _transform_transform(new_abd, new_w)

        # Model fit in the Enterosignatures paper is the cosine similarity
        # between genus abundance and model
        # So for sample i, between (WH)_i and (N_w)_i
        mf: pd.DataFrame = _transform_model_fit(new_w, es, new_abd)

        # Zip up new W, new abundance, new H (enterosig weights), and model fit
        res_zip: io.BytesIO = _zip_items([
            ("w.tsv", new_w.to_csv(sep="\t")),
            ("h.tsv", es.to_csv(sep="\t")),
            ("abundance.tsv", new_abd.to_csv(sep="\t")),
            ("model_fit.tsv", mf.to_csv(sep="\t")),
            ("taxon_mapping.tsv", mapping.to_df().to_csv(sep="\t")),
            ("log.txt", es_log.to_file())
        ])

        with expander_results: 
            st.download_button(
                label = text.DOWNLOAD_LABEL,
                data = res_zip,
                file_name = "apply_es_results.zip"
            )

            st.markdown(text.RESULTS)

            st.markdown(text.WEIGHT_PLOT_TITLE)
            # Provide a simple visualisations of the ES
            p_hmap: go.Figure = _plot_heatmap(es)
            st.plotly_chart(
                p_hmap
            )

            # Provide a simple visualisation of the model fit
            # TODO(apduncan): Bin count customisation, spline, explain fit
            st.markdown(text.MODELFIT_PLOT_TITLE)
            p_hist: go.Figure = _plot_hist(mf)
            st.plotly_chart(
                p_hist
            )

            st.session_state.uploaded = True

    except EnteroException as err:
        st.write(f"Unable to transform: {err}")
