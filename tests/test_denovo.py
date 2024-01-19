"""Tests for denovo ES generation."""
import itertools
import pathlib
from typing import List

import numpy as np
import pandas as pd
import pytest

from enterosig import models
from enterosig.denovo import BicvSplit, BicvFold, bicv, _cosine_similarity, rank_selection


def test_bicv_split():
    """Shuffling and splitting working as intended?"""
    df: pd.DataFrame = models.example_abundance()
    shuffles: List[BicvSplit] = BicvSplit.from_matrix(
        df=df, n=2, random_state=4298
    )

    # Overall number of entries in matrix is consistent
    shuf_len: int = shuffles[0].size
    assert shuf_len == df.size, \
        "Shuffled and split matrix different size to input"

    # Number of columns and rows consistent
    shuf_cols: int = shuffles[0].shape[1]
    shuf_rows: int = shuffles[0].shape[0]
    assert shuf_rows == df.shape[0], "Split and input shapes inconsistent"
    assert shuf_cols == df.shape[1], "Split and input shapes inconsistent"

    # Sum of entries consistent
    entry_sum: float = shuffles[0].x.sum().sum()
    assert np.isclose(entry_sum, df.sum().sum()), \
        "Sum of values in split and input are inconsistent"

    # Sorted list of entries as consistent
    input_vals: np.ndarray = np.sort(df.values.ravel())
    shuffled_vals: np.ndarray = np.sort(shuffles[0].x.values.ravel())
    assert all(np.isclose(input_vals, shuffled_vals))

    # Check we did actually shuffle the indices
    assert not all(shuffles[0].x.index == df.index), \
        "Index not shuffled"
    assert not all(shuffles[0].x.columns == df.columns), \
        "Columns not shuffled"

    # Get folds
    shuffles[0].fold(0)


def test_bicv_folds():
    """Are folds be made from submatrices correctly?"""
    df: pd.DataFrame = models.example_abundance()
    shuffle: BicvSplit = BicvSplit.from_matrix(
        df=df, n=1, random_state=4298
    )[0]
    folds: List[BicvFold] = [shuffle.fold(i) for i in range(9)]

    def fold_sum(fold) -> float:
        return sum(x.sum().sum() for x in fold)

    # Check each fold has expected naming etc.
    for fold in folds:
        # No values should be NA
        for key, val in fold._asdict().items():
            assert not val.isna().any().any(), \
                f"NAs introduced in matrix {key} during fold generation"
        # B and D should share column names and order
        assert all(fold.B.columns == fold.D.columns), \
            "Columns not matched between B and D"
        # A and B should share index names and order
        assert all(fold.A.index == fold.B.index), \
            "Index not matched between A and B"
        # A and C should share column names and order
        assert all(fold.A.columns == fold.C.columns), \
            "Columns not matched between A and C"
        # C and D should share index names and order
        assert all(fold.C.index == fold.D.index), \
            "Columns not matched between C and D"

        # Check sum equal to input
        assert np.isclose(fold_sum(fold), df.sum().sum()), \
            "Sum of values in fold not equal to sum of input matrix"

    # Check no folds are identical
    for a, b in itertools.combinations(folds, 2):
        assert not np.array_equal(a, b), \
            "Two folds were equal"


def test_bicv_split_io(tmp_path: pathlib.Path):
    """Test BicvSplit I/O"""

    df: pd.DataFrame = models.five_es()
    shuffles: List[BicvSplit] = BicvSplit.from_matrix(
        df=df, n=2, random_state=4298
    )

    # Basic operations
    # Save single shuffle
    shuffles[0].save_npz(tmp_path)
    assert tmp_path.with_name("shuffle_0.npz"), \
        "Saving a single shuffle failed"
    # Error on unforced overwrite
    with pytest.raises(FileExistsError):
        shuffles[0].save_npz(tmp_path)
    # Output all with force
    BicvSplit.save_all_npz(shuffles, tmp_path, force=True)
    # Count number of output files
    num_written: int = len(list(tmp_path.glob("shuffle_*.npz")))
    assert num_written == len(shuffles), \
        "Incorrect number of files written by save_all_npz"

    # Load single
    shuffle_0 = BicvSplit.load_npz(tmp_path / "shuffle_0.npz")
    # Check these are equivalent
    assert all(np.isclose(shuffle_0.x.values, shuffles[0].x.values).ravel()), \
        "Loaded object is not equivalent to source object"
    # Load multiple
    shuffles_loaded: List[BicvSplit] = BicvSplit.load_all_npz(tmp_path)
    # Should be equal to shuffles
    assert all(
        np.array_equal(a.x.values, b.x.values)
        for a, b in zip(shuffles, shuffles_loaded)
    ), \
        "Loaded matrices not equivalent to those saved"


def test_bicv():
    df: pd.DataFrame = models.five_es_x()
    shuffles: List[BicvSplit] = BicvSplit.from_matrix(
        df=df, n=1, random_state=4298)

    res = bicv(mx=shuffles[0], rank=5, seed=99)
    # TODO: Complete tests, only checks for execution without error currently


def test__cosine_similarity():
    a: np.ndarray = np.array([1.0, 0.0, 2.0, 0.5])
    assert _cosine_similarity(a, a) == 1.0, \
        "Similarity between identical vectors must be 1.0"
    # Should ignore scale
    assert _cosine_similarity(a, a * 2) == 1.0, \
        "Not scale invariant"
    # Should be -1 for inverse vector
    assert _cosine_similarity(a, -a) == -1.0, \
        "Should be -1 for inverse"


def test_rank_selection():
    df: pd.DataFrame = models.example_abundance()
    rank_selection(df, list(range(2, 6)), 5)
