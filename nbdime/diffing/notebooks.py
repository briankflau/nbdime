# coding: utf-8

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import unicode_literals

"""Tools for diffing notebooks.

All diff tools here currently assumes the notebooks have already been
converted to the same format version, currently v4 at time of writing.
Up- and down-conversion is handled by nbformat.
"""

import difflib
import operator

from ..dformat import PATCH, SEQINSERT, SEQDELETE
from ..dformat import decompress_diff

from .comparing import strings_are_similar
from .sequences import diff_sequence
from .generic import diff, diff_lists, diff_dicts
from .snakes import diff_sequence_multilevel

__all__ = ["diff_notebooks"]


def compare_cell_source_approximate(x, y):
    "Compare source of cells x,y with approximate heuristics."
    # Cell types must match
    if x["cell_type"] != y["cell_type"]:
        return False

    # Convert from list to single string
    xs = x["source"]
    ys = y["source"]
    if isinstance(xs, list):
        xs = "\n".join(xs)
    if isinstance(ys, list):
        ys = "\n".join(ys)

    # Cutoff on equality (Python has fast hash functions for strings)
    if xs == ys:
        return True

    # TODO: Investigate performance and quality of this difflib ratio approach,
    # possibly one of the weakest links of the notebook diffing algorithm.
    # Alternatives to try are the libraries diff-patch-match and Levenschtein
    threshold = 0.7  # TODO: Add configuration framework and tune with real world examples?

    # Informal benchmark normalized to operator ==:
    #    1.0  operator ==
    #  438.2  real_quick_ratio
    #  796.5  quick_ratio
    # 3088.2  ratio
    # The == cutoff will hit most of the time for long runs of
    # equal items, at least in the Myers diff algorithm.
    # Most other comparisons will likely not be very similar,
    # and the (real_)quick_ratio cutoffs will speed up those.
    # So the heavy ratio function is only used for close calls.
    #s = difflib.SequenceMatcher(lambda c: c in (" ", "\t"), x, y, autojunk=False)
    s = difflib.SequenceMatcher(None, xs, ys, autojunk=False)
    if s.real_quick_ratio() < threshold:
        return False
    if s.quick_ratio() < threshold:
        return False
    return s.ratio() > threshold


def compare_cell_source_exact(x, y):
    "Compare source of cells x,y exactly."
    if x["cell_type"] != y["cell_type"]:
        return False
    if x["source"] != y["source"]:
        return False
    return True


def compare_cell_source_and_outputs(x, y):
    "Compare source and outputs of cells x,y exactly."
    if x["cell_type"] != y["cell_type"]:
        return False
    if x["source"] != y["source"]:
        return False
    if x["cell_type"] == "code" and x["outputs"] != y["outputs"]:
        return False
    # NB! Ignoring metadata and execution count
    return True


def compare_output_type(x, y):
    "Compare only type of output cells x,y."
    if x["output_type"] != y["output_type"]:
        return False
    # NB! Ignoring metadata and execution count
    return True


def compare_output_data_keys(x, y):
    "Compare type and data of output cells x,y exactly."
    if x["output_type"] != y["output_type"]:
        return False
    if set(x["data"].keys()) != set(y["data"].keys()):
        return False
    # NB! Ignoring metadata and execution count
    return True


def compare_output_data(x, y):
    "Compare type and data of output cells x,y exactly."
    if x["output_type"] != y["output_type"]:
        return False
    # Keys are potentially a lot cheaper to compare than values
    if set(x["data"].keys()) != set(y["data"].keys()):
        return False
    if x["data"] != y["data"]:
        return False
    # NB! Ignoring metadata and execution count
    return True


def diff_source(a, b, compare="ignored"):
    "Diff a pair of sources."
    # TODO: Use google-diff-patch-match library to diff the sources?
    return diff(a, b)


def diff_single_outputs(a, b, compare="ignored"):
    "Diff a pair of output cells."
    # TODO: Handle output diffing with plugins? I.e. image diff, svg diff, json diff, etc.
    return diff(a, b)


def diff_outputs(a, b, compare="ignored"):
    "Diff a pair of lists of outputs from within a single cell."
    return diff_sequence_multilevel(a, b,
                                    predicates=[compare_output_data_keys, compare_output_data],
                                    subdiff=diff_single_outputs)


def diff_single_cells(a, b):
    return diff_dicts(a, b, subdiffs={"source": diff_source, "outputs": diff_outputs})


def diff_cells(a, b, compare="ignored"):
    "Diff cell lists a and b. Argument compare is ignored."
    # Predicates to compare cells in order of low-to-high precedence
    predicates = [compare_cell_source_approximate,
                  compare_cell_source_exact,
                  compare_cell_source_and_outputs]
    return diff_sequence_multilevel(a, b, predicates, diff_single_cells)


def old_diff_cells(cells_a, cells_b):
    "Compute the diff of two sequences of cells."
    shallow_diff = diff_sequence(cells_a, cells_b, compare_cells)
    return diff_lists(cells_a, cells_b, compare=operator.__eq__, shallow_diff=shallow_diff)


def diff_notebooks(nba, nbb):
    """Compute the diff of two notebooks."""
    return diff_dicts(nba, nbb, subdiffs={"cells": diff_cells})
