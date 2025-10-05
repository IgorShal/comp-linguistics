import pytest
from typing import Any, Dict, List, Optional

# Adjust import path if your module name is different
from repositories.neo4j_repository import Neo4jRepository
from utils.repository_error import RepositoryError


# ===== Fake Neo4j objects for testing =====
class FakeNode:
    def __init__(self, props: Dict[str, Any], eid: Optional[str] = None):
        self._props = dict(props)
        # emulate element_id attribute used by collect_node
        self.element_id = eid or f"node_{self._props.get('uri', 'no_uri')}"

    def keys(self):
        return list(self._props.keys())

    def __getitem__(self, key):
        return self._props.get(key)

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __iter__(self):
        return iter(self._props.items())


class FakeRel:
    def __init__(self, start: FakeNode, end: FakeNode, rel_type: str, props: Optional[Dict[str, Any]] = None,
                 eid: Optional[str] = None):
        self.element_id = eid or f"rel_{rel_type}_{start.get('uri')}_{end.get('uri')}"
        self.type = rel_type
        self._props = dict(props or {})
        self.start_node = start
        self.end_node = end

    def keys(self):
        return list(self._props.keys())

    def __getitem__(self, key):
        return self._props.get(key)


class FakeRecord:
    def __init__(self, mapping: Dict[str, Any]):
        self._map = mapping

    def get(self, key, default=None):
        return self._map.get(key, default)

    def __getitem__(self, key):
        return self._map[key]

    def keys(self):
        return list(self._map.keys())


class FakeResult:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = [FakeRecord(r) for r in rows]

    def single(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self, results_queue: List[FakeResult]):
        # shared queue reference so multiple sessions consume the same prepared results
        self._results_queue = results_queue
        self.ran = []

    def run(self, query: str, params: Optional[Dict[str, Any]] = None):
        # record call for debugging
        self.ran.append((query, params))
        if not self._results_queue:
            # return empty result
            return FakeResult([])
        return self._results_queue.pop(0)

    def close(self):
        pass

    # context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeDriver:
    def __init__(self, results_queue: Optional[List[FakeResult]] = None):
        self._results_queue = results_queue or []
        self.sessions = []

    def session(self):
        s = FakeSession(self._results_queue)
        self.sessions.append(s)
        return s

    def close(self):
        pass


# ===== Helpers to create fake nodes/relations/results =====

def make_node_record(uri: str, title: Optional[str] = None, description: Optional[str] = None):
    props = {"uri": uri}
    if title is not None:
        props["title"] = title
    if description is not None:
        props["description"] = description
    return {"n": FakeNode(props)}


def make_node_record_named(key: str, uri: str, title: Optional[str] = None, description: Optional[str] = None):
    props = {"uri": uri}
    if title is not None:
        props["title"] = title
    if description is not None:
        props["description"] = description
    return {key: FakeNode(props)}


# ===== Tests =====

def test_transform_labels_and_props():
    repo = Neo4jRepository("bolt://x", "u", "p")
    assert repo.transform_labels(["One", "Two"]) == "`One`:`Two`"
    assert repo.transform_labels([]) == ""

    cy, params = repo.transform_props({"a": 1})
    assert cy == "{props_map}"
    assert params == {"props_map": {"a": 1}}


def test_create_node_and_get_node_by_uri_and_title():
    # prepare a fake result for CREATE (returns n)
    node = FakeNode({"uri": "u1", "title": "T1", "description": "D1"})
    results = [FakeResult([{"n": node}])]
    driver = FakeDriver(results)

    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = driver

    created = repo.create_node({"title": "T1", "description": "D1"}, labels=["LabelA"])
    assert created["uri"] == "u1"
    assert created["title"] == "T1"

    # get_node_by_uri should consume another run; prepare response
    driver._results_queue.append(FakeResult([{"n": node}]))
    got = repo.get_node_by_uri("u1")
    assert got["uri"] == "u1"

    # get_node_by_title uses MATCH with title, prepare uri result
    # _find_node_uri_by_title returns uri via session.run -> return record with 'uri'
    driver._results_queue.append(FakeResult([{"uri": "u1"}]))
    repo._driver = driver
    res = repo._find_node_uri_by_title(None, "T1")
    assert res == "u1"


def test_create_arc_and_collect_arc():
    # create two nodes and a relation
    a = FakeNode({"uri": "a1"})
    b = FakeNode({"uri": "b1"})
    rel = FakeRel(a, b, "RELATED", props={"weight": 5})
    results = [FakeResult([{"r": rel, "a": a, "b": b}])]
    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver(results)

    arc = repo.create_arc("a1", "b1", rel_type="RELATED", props={"weight": 5})
    assert arc["uri"] == "RELATED"
    assert arc["node_uri_to"] == "b1"
    assert arc["node_uri_from"] == "a1"
    assert arc["props"]["weight"] == 5


def test_create_arc_by_titles_delegates_and_errors(monkeypatch):
    repo = Neo4jRepository("bolt://x", "u", "p")
    # monkeypatch resolver
    monkeypatch.setattr(repo, "_find_node_uri_by_title", lambda label, title: ("u1" if title == "A" else "u2"))
    called = {}

    def fake_create_arc(u1, u2, rel_type=None, props=None):
        called['args'] = (u1, u2, rel_type, props)
        return {"ok": True}

    monkeypatch.setattr(repo, "create_arc", fake_create_arc)
    res = repo.create_arc_by_titles("A", "B", rel_type="R")
    assert res == {"ok": True}
    assert called['args'][0] == "u1"
    assert called['args'][1] == "u2"

    # missing title should raise
    monkeypatch.setattr(repo, "_find_node_uri_by_title", lambda l, t: None)
    with pytest.raises(RepositoryError):
        repo.create_arc_by_titles("X", "Y")


def test_get_all_nodes_and_arcs():
    # prepare one node with two arcs (one relation, one None)
    n1 = FakeNode({"uri": "n1", "title": "N1"})
    r = FakeRel(n1, FakeNode({"uri": "n2"}), "LINKS")
    arcs_entry = {"r": r, "m": FakeNode({"uri": "n2"})}
    results = [FakeResult([{"n": n1, "arcs": [arcs_entry]}])]

    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver(results)

    out = repo.get_all_nodes_and_arcs()
    assert isinstance(out, list)
    assert out[0]["uri"] == "n1"
    assert "arcs" in out[0]
    assert out[0]["arcs"][0]["uri"] == "LINKS"


def test_get_nodes_by_labels_and_errors():
    repo = Neo4jRepository("bolt://x", "u", "p")
    # empty labels should raise
    with pytest.raises(RepositoryError):
        repo.get_nodes_by_labels([])


def test_delete_node_and_arc_by_id():
    # delete_node_by_uri
    results = [FakeResult([{"cnt": 1}])]
    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver(results)
    assert repo.delete_node_by_uri("u1") is True

    # delete_arc_by_element_id
    repo._driver = FakeDriver([FakeResult([{"cnt": 1}])])
    assert repo.delete_arc_by_element_id("rid") is True


def test_update_node_sets_and_labels():
    # prepare returned node
    n = FakeNode({"uri": "u1", "title": "New"})
    results = [FakeResult([{"n": n}])]
    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver(results)

    updated = repo.update_node("u1", {"title": "New"}, set_labels=["L1"], remove_labels=["L2"])
    assert updated["uri"] == "u1"
    assert updated["title"] == "New"


def test_class_crud_and_attributes(monkeypatch):
    # create_class without parent - monkeypatch collect_signature
    n = FakeNode({"uri": "c1", "title": "C1"})
    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver([FakeResult([{"c": n}])])
    monkeypatch.setattr(repo, "collect_signature", lambda uri: {"params": [], "obj_params": []})
    created = repo.create_class("C1", description="d1")
    assert created["uri"] == "c1"
    assert "signature" in created

    # get_class (returns c and calls collect_signature) - monkeypatch collect_signature
    repo._driver = FakeDriver([FakeResult([{"c": n}])])
    monkeypatch.setattr(repo, "collect_signature", lambda uri: {"params": [], "obj_params": []})
    got = repo.get_class("c1")
    assert got["uri"] == "c1"
    assert "signature" in got

    # add_class_attribute
    repo._driver = FakeDriver([FakeResult([{"p": FakeNode({"uri": "p1", "title": "name"})}])])
    # monkeypatch find
    monkeypatch.setattr(repo, "_find_node_by_title", lambda label, title: {"uri": "c1"})
    prop = repo.add_class_attribute("C1", prop_title="name")
    assert prop["uri"] == "p1"

    # delete_class_attribute
    repo._driver = FakeDriver([FakeResult([{"cnt": 1}])])
    assert repo.delete_class_attribute("p1") is True

    # add_class_object_attribute with range
    repo._driver = FakeDriver([FakeResult([{"p": FakeNode({"uri": "op1", "title": "rel"})}]), FakeResult([])])
    monkeypatch.setattr(repo, "_find_node_by_title", lambda label, title: {"uri": "c1"} if label == repo.CLASS_LABEL and title == "C1" else {"uri": "c2"})
    op = repo.add_class_object_attribute("C1", attr_title="rel", range_class_title="C2")
    assert op["uri"] == "op1"

    # delete_class_object_attribute - prepare del node returns cnt
    repo._driver = FakeDriver([FakeResult([]), FakeResult([{"cnt": 1}])])
    assert repo.delete_class_object_attribute("op1") is True


def test_add_class_parent_and_errors(monkeypatch):
    repo = Neo4jRepository("bolt://x", "u", "p")
    # monkeypatch _find_node_uri_by_title
    monkeypatch.setattr(repo, "_find_node_uri_by_title", lambda label, title: ("p_uri" if title == "P" else "t_uri"))
    # monkeypatch create_arc
    monkeypatch.setattr(repo, "create_arc", lambda a, b, rel_type=None, props=None: True)
    assert repo.add_class_parent("P", "T") is True
    # when not found
    monkeypatch.setattr(repo, "_find_node_uri_by_title", lambda l, t: None)
    assert repo.add_class_parent("X", "Y") is False




def test_create_and_get_object(monkeypatch):
    # create_object should create node and set TYPE relationship
    o = FakeNode({"uri": "o1", "title": "Obj1"})
    results = [FakeResult([{"o": o}]), FakeResult([])]  # one for CREATE, one for TYPE relation
    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver(results)
    # monkeypatch find class
    monkeypatch.setattr(repo, "_find_node_by_title", lambda label, title: {"uri": "c1"})
    created = repo.create_object("SomeClass", obj_title="Obj1", datatype_props={"name": "N"})
    assert created["uri"] == "o1"

    # get_object - monkeypatch get_node_by_uri and simulate class match
    node = {"uri": "o1", "class_uri": "c1"}
    monkeypatch.setattr(repo, "get_node_by_uri", lambda uri: node)
    # prepare session run returning no class via relationship
    repo._driver = FakeDriver([FakeResult([])])
    got = repo.get_object("o1")
    assert got["uri"] == "o1"
    assert "class" in got  # ensure field exists
    assert isinstance(got["class"], dict) or got["class"] is None


def test_update_object_add_and_remove(monkeypatch):
    repo = Neo4jRepository("bolt://x", "u", "p")
    # monkeypatch find property and target nodes
    monkeypatch.setattr(repo, "_find_node_by_title", lambda label, title: {"uri": "prop_uri"} if label in (repo.OBJECT_PROPERTY_LABEL, repo.DATATYPE_PROPERTY_LABEL) else {"uri": "target_uri"})
    # monkeypatch create_arc and get_object
    monkeypatch.setattr(repo, "create_arc", lambda a, b, rel_type=None, props=None: True)
    monkeypatch.setattr(repo, "get_object", lambda uri: {"uri": uri, "title": "X"})
    # Prepare session results for SET and deletes; each run returns something but we don't assert those
    repo._driver = FakeDriver([FakeResult([{"o": FakeNode({"uri": "o1"})}])])
    updated = repo.update_object("o1", title="New", obj_params_to_add=[{"prop_title": "p", "target_title": "t"}], obj_params_to_remove=[{"prop_title": "p", "target_title": "t"}])
    assert updated["uri"] == "o1"


def test_collect_signature_aggregates_properties():
    # Simulate 4 runs: dt, dt_inherited, obj_forward, obj_backward
    p1 = FakeNode({"uri": "p1", "title": "name"})
    p2 = FakeNode({"uri": "p2", "title": "age"})
    op = FakeNode({"uri": "op1", "title": "rel"})
    cls = FakeNode({"uri": "c2", "title": "Target"})
    results = [
        FakeResult([{"p": p1}]),
        FakeResult([{"p": p2}]),
        FakeResult([{"p": op, "r": cls}]),
        FakeResult([])
    ]
    repo = Neo4jRepository("bolt://x", "u", "p")
    repo._driver = FakeDriver(results)

    sig = repo.collect_signature("c1")
    assert "params" in sig and "obj_params" in sig
    assert any(p.get("url") == "p1" for p in sig["params"])
    assert any(o.get("url") == "op1" for o in sig["obj_params"])


# If you want to run the tests directly via `python test_neo4j_repository.py`
if __name__ == "__main__":
    pytest.main([__file__])
