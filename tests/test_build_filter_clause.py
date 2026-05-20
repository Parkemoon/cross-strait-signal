"""Unit tests for the central WHERE-clause builder used by the stats API.

_build_filter_clause is the contract between the dashboard's scoping filters
and the SQL aggregations. Bugs here silently produce wrong gauge values.
"""
from api.routes.stats import _build_filter_clause


def test_no_filters_returns_empty_clause():
    sql, params = _build_filter_clause()
    assert sql == ""
    assert params == []


def test_topic_filter():
    sql, params = _build_filter_clause(topic="MIL_EXERCISE")
    assert "ai.topic_primary = ?" in sql
    assert params == ["MIL_EXERCISE"]


def test_source_place_prc():
    sql, params = _build_filter_clause(source_place="PRC")
    assert "s.place = ?" in sql
    assert params == ["PRC"]


def test_source_place_tw_uppercase_normalised():
    sql, params = _build_filter_clause(source_place="tw")
    assert "s.place = ?" in sql
    assert params == ["TW"]


def test_source_place_hk_maps_to_hk_mo():
    sql, params = _build_filter_clause(source_place="hk")
    assert "s.place IN ('HK', 'MO')" in sql
    assert params == []


def test_source_place_intl_excludes_strait_places():
    sql, params = _build_filter_clause(source_place="intl")
    assert "NOT IN" in sql
    assert "'PRC'" in sql and "'TW'" in sql
    assert params == []


def test_source_name_uses_like_prefix_match():
    sql, params = _build_filter_clause(source_name="LTN")
    assert "s.name LIKE ?" in sql
    assert params == ["LTN%"]


def test_bias_filter():
    sql, params = _build_filter_clause(bias="green")
    assert "s.bias = ?" in sql
    assert params == ["green"]


def test_escalation_only_uses_no_param():
    sql, params = _build_filter_clause(escalation_only=True)
    assert "ai.is_escalation_signal = 1" in sql
    assert params == []


def test_escalation_only_false_does_nothing():
    sql, params = _build_filter_clause(escalation_only=False)
    assert sql == ""
    assert params == []


def test_entity_uses_exists_subquery():
    """Entity filter must use EXISTS so the outer query doesn't double-join."""
    sql, params = _build_filter_clause(entity="Xi Jinping")
    assert "EXISTS (SELECT 1 FROM entities e" in sql
    assert params == ["%Xi Jinping%", "%Xi Jinping%"]


def test_multiple_filters_compose_with_and():
    sql, params = _build_filter_clause(topic="MIL_EXERCISE", bias="green", urgency="priority")
    assert sql.count(" AND ") == 3  # leading " AND " + 2 between clauses
    assert "MIL_EXERCISE" in params
    assert "green" in params
    assert "priority" in params


def test_sql_fragment_starts_with_and_when_clauses_present():
    """Callers concatenate this onto an existing WHERE — the leading AND matters."""
    sql, _ = _build_filter_clause(topic="ECON_TRADE")
    assert sql.startswith(" AND ")
