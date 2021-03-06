# coding: utf-8

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import unicode_literals

from six import string_types
from six.moves import xrange as range
import operator
from collections import defaultdict

from ..diff_format import validate_diff, count_consumed_symbols
from ..diff_format import SequenceDiffBuilder, MappingDiffBuilder

from .sequences import diff_strings, diff_sequence
from .snakes import compute_snakes_multilevel, compute_diff_from_snakes

__all__ = ["diff"]


def is_atomic(x):
    "Return True for values that diff should treat as a single atomic value."
    return not isinstance(x, (string_types) + (list, dict))


def default_predicates():
    return defaultdict(lambda: (operator.__eq__,))


def default_differs():
    return defaultdict(lambda: diff)


def diff(a, b, path="", predicates=None, differs=None):
    "Compute the diff of two json-like objects, list or dict or string."

    if predicates is None:
        predicates = default_predicates()
    if differs is None:
        differs = default_differs()

    if isinstance(a, list) and isinstance(b, list):
        d = diff_lists(a, b, path=path, predicates=predicates, differs=differs)
    elif isinstance(a, dict) and isinstance(b, dict):
        d = diff_dicts(a, b, path=path, predicates=predicates, differs=differs)
    elif isinstance(a, string_types) and isinstance(b, string_types):
        # FIXME: Do we need this string case, and if so do we need to pass on these additional arguments?
        d = diff_strings(a, b) #, path=path, predicates=predicates, differs=differs)
    else:
        raise RuntimeError("Can currently only diff list, dict, or str objects.")

    # We can turn this off for performance after the library has been well tested:
    validate_diff(d)

    return d


def diff_sequence_multilevel(a, b, path="", predicates=None, differs=None):
    """Compute diff of two lists with configurable behaviour."""

    if predicates is None:
        predicates = default_predicates()
    if differs is None:
        differs = default_differs()

    # Invoke multilevel snake computation algorithm
    compares = predicates[path]
    snakes = compute_snakes_multilevel(a, b, compares)

    # Convert snakes to diff
    return compute_diff_from_snakes(a, b, snakes, path=path, predicates=predicates, differs=differs)


def diff_lists(a, b, path="", predicates=None, differs=None, shallow_diff=None):
    """Compute diff of two lists with configurable behaviour."""

    if predicates is None:
        predicates = default_predicates()
    if differs is None:
        differs = default_differs()

    # If multiple compares are provided to this path, delegate to multilevel algorithm
    compares = predicates[path]
    if len(compares) > 1:
        assert shallow_diff is None
        return diff_sequence_multilevel(a, b, path=path, predicates=predicates, differs=differs)

    # First make a shallow sequence diff with custom compare,
    # unless it's provided for us
    if shallow_diff is None:
        shallow_diff = diff_sequence(a, b, compares[0])

    # Next we recurse to diff items in sequence that are considered
    # similar by compares[0] in the loop below
    subpath = "/".join((path, "*"))
    diffit = differs.get(subpath, diff)

    # Count consumed items i,j from a,b, (i="take" in patch_list)
    i, j = 0, 0
    di = SequenceDiffBuilder()
    M = len(shallow_diff)
    for ie in range(M+1):
        if ie < M:
            # Consume n more unmentioned items before this diff entry
            # Note that index can be larger than i in the case where items
            # have been deleted from a and then insertions from b occur.
            e = shallow_diff[ie]
            index = e.key
            n = max(0, index - i)
            askip, bskip = count_consumed_symbols(e)
        else:
            # Consume final items after the last diff entry
            e = None
            n = len(a) - i
            askip, bskip = 0, 0
            assert n >= 0
            assert len(b) - j == n

        # Recursively diff the n items that have been deemed similar
        for k in range(n):
            aval = a[i + k]
            bval = b[j + k]
            if not is_atomic(aval):
                cd = diffit(aval, bval, path=subpath, predicates=predicates, differs=differs)
                if cd:
                    di.patch(i + k, cd)  # FIXME: Not covered in tests, create test situation

        # Keep count of consumed items
        i += n + askip
        j += n + bskip

        # Insert the diff entry from shallow diff unless past the end
        # (this either adds or removes items)
        if ie < M:
            di.append(e)

    # Sanity check
    assert i == len(a)
    assert j == len(b)

    return di.validated()


def diff_dicts(a, b, path="", predicates=None, differs=None):
    """Compute diff of two dicts with configurable behaviour.

    Keys in both a and b will be handled based on

    Make a one-level diff of dicts a and b, using given compare
    operator to specify which items are considered the same.

    Items not mentioned in diff are items where compare(x, y) return True.
    For other items the diff will contain delete, insert, or replace entries.
    """
    if predicates is None:
        predicates = default_predicates()
    if differs is None:
        differs = default_differs()

    assert isinstance(a, dict) and isinstance(b, dict)
    akeys = set(a.keys())
    bkeys = set(b.keys())

    di = MappingDiffBuilder()

    # Sorting keys in loops to get a deterministic diff result
    for key in sorted(akeys - bkeys):
        di.remove(key)

    # Handle values for keys in both a and b
    for key in sorted(akeys & bkeys):
        avalue = a[key]
        bvalue = b[key]
        # If types are the same and nonatomic, recurse
        if type(avalue) == type(bvalue) and not is_atomic(avalue):
            subpath = "/".join((path, key))
            diffit = differs.get(subpath, diff)
            dd = diffit(avalue, bvalue, path=subpath, predicates=predicates, differs=differs)
            if dd:
                di.patch(key, dd)
        else:
            if path in predicates:
                # Could also this a warning, but I think it shouldn't be done
                raise RuntimeError("Found predicate(s) for path {} pointing to dict entry.".format(path))
            if avalue != bvalue:
                di.replace(key, bvalue)

    for key in sorted(bkeys - akeys):
        di.add(key, b[key])

    return di.validated()
