"""Tests for saved searches + new-match diffing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobfinder.saved_searches import SavedSearch, new_saved_search, register_run, mark_seen


def test_new_saved_search_from_request():
    s = new_saved_search("Python remote", {"cv_id": "cv1", "keywords": "python",
                                           "sources": ["remotive", "arbeitnow"], "remote": True, "limit_per_source": 10})
    assert s.name == "Python remote" and s.cv_id == "cv1" and s.keywords == "python"
    assert s.sources == ["remotive", "arbeitnow"] and s.remote is True and s.limit_per_source == 10
    assert s.new_count == 0 and s.seen_ids == [] and s.id


def test_register_run_diffs_and_accumulates_until_seen():
    s = new_saved_search("S", {})
    assert set(register_run(s, ["a", "b", "c"])) == {"a", "b", "c"}
    assert s.new_count == 3 and set(s.seen_ids) == {"a", "b", "c"} and s.last_run

    assert register_run(s, ["b", "c", "d"]) == ["d"]      # only d is new
    assert s.new_count == 4                                # unviewed accumulates (3 + 1)

    mark_seen(s)
    assert s.new_count == 0
    assert register_run(s, ["a", "b", "c", "d"]) == []     # nothing new on a repeat run
    assert s.new_count == 0


def test_seen_ids_are_bounded():
    s = new_saved_search("S", {})
    register_run(s, [str(i) for i in range(1500)])
    assert len(s.seen_ids) <= 1000
    assert "1499" in s.seen_ids                            # keeps the most recent


def test_from_dict_ignores_unknown_keys():
    s = SavedSearch.from_dict({"name": "N", "keywords": "k", "mystery": 1, "id": "x"})
    assert s.name == "N" and s.keywords == "k" and s.id == "x"
