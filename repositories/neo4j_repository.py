
import json
import uuid
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase, Driver

from utils.helpers import _safe_label, TNode, TArc, _LABEL_RE
from utils.repository_error import RepositoryError


class Neo4jRepository:
    def __init__(self, uri: str, user: str, password: str, encrypted: bool = False,
                 base_uri: str = "http://localhost:7474/db/data/node/"):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password), encrypted=encrypted)
        self.base_uri = base_uri.rstrip("/") + "/"

    def close(self):
        self._driver.close()

    def generate_random_string(self) -> str:
        """Generate a reasonably unique string for uri values."""
        return uuid.uuid4().hex

    def transform_labels(self, labels: List[str], separator: str = ':') -> str:
        """
        transform list of labels into cypher label string like `Label1`:`Label2`
        Raises RepositoryError on invalid label.
        """
        if not labels:
            return ''
        return separator.join(_safe_label(l) for l in labels)

    def transform_props(self, props: Dict[str, Any]) -> (str, Dict[str, Any]):
        """
        Returns tuple (cypher_text, params) where cypher_text can be used like:
            SET n += {props}
        or as node properties in CREATE:
            CREATE (n {props_map})
        and params is the dictionary to pass to session.run
        This avoids direct inline JSON building and keeps params safe.
        """
        if not props:
            return "", {}
        return "{props_map}", {"props_map": props}

    def get_all_nodes(self) -> List[TNode]:
        q = "MATCH (n) RETURN n"
        with self._driver.session() as sess:
            res = sess.run(q)
            nodes = []
            for r in res:
                n = r["n"]
                nodes.append(self.collect_node(n))
            return nodes

    def get_all_nodes_and_arcs(self) -> List[TNode]:
        """
        Returns list of nodes, each node dict may include 'arcs': list of arcs outgoing from this node.
        If a node has no outgoing arcs, arcs will be absent.
        """
        q = """
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN n, collect(r) as rels, collect(m) as targets
        """
        with self._driver.session() as sess:
            res = sess.run(q)
            out = []
            for r in res:
                n = r["n"]
                rels = r["rels"] or []
                targets = r["targets"] or []
                node_dict = self.collect_node(n)
                arcs_list = []
                for rel, target in zip(rels, targets):
                    if rel is None:
                        continue
                    arc = self.collect_arc(rel, target_node=target)
                    arcs_list.append(arc)
                if arcs_list:
                    node_dict["arcs"] = arcs_list
                out.append(node_dict)
            return out

    def get_nodes_by_labels(self, labels: List[str]) -> List[TNode]:
        """
        labels: list of label names (strings).
        """
        labels_cy = self.transform_labels(labels, separator=':')
        if labels_cy == '':
            raise RepositoryError("labels list empty")
        q = f"MATCH (n:{labels_cy}) RETURN n"
        with self._driver.session() as sess:
            res = sess.run(q)
            return [self.collect_node(r["n"]) for r in res]

    def get_node_by_uri(self, uri: str) -> Optional[TNode]:
        q = "MATCH (n) WHERE n.uri = $uri RETURN n LIMIT 1"
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": uri})
            rec = res.single()
            if not rec:
                return None
            return self.collect_node(rec["n"])

    def create_node(self, params: Dict[str, Any], labels: Optional[List[str]] = None) -> TNode:
        """
        params: properties dictionary for the node. If params doesn't contain 'uri', one will be generated.
        labels: optional list of labels to assign to node.
        Returns created node dict.
        """
        if "uri" not in params:
            params["uri"] = self.base_uri + self.generate_random_string()
        elif not params["uri"].startswith("http"):
            params["uri"] = self.base_uri + params["uri"]
        label_part = ''
        if labels:
            label_part = ':' + self.transform_labels(labels, separator=':')
        props_text, cy_params = self.transform_props(params)
        q = f"CREATE (n{label_part} $props) RETURN n"
        with self._driver.session() as sess:
            res = sess.run(q, {"props": params})
            rec = res.single()
            n = rec["n"]
            return self.collect_node(n)

    def create_arc(self, node1_uri: str, node2_uri: str, rel_type: str = "RELATED", props: Optional[Dict[str, Any]] = None) -> TArc:
        """
        Create directed arc (node1)-[r:RELTYPE {props}]->(node2).
        rel_type will be validated (only letters/numbers/_ allowed).
        Returns created arc dict.
        """
        if not node1_uri.startswith("http"):
            node1_uri = self.base_uri + node1_uri
        if not node2_uri.startswith("http"):
            node2_uri = self.base_uri + node2_uri
        rel_type_safe = rel_type if _LABEL_RE.match(rel_type) else "RELATED"
        props = props or {}
        rel_type_cy = _safe_label(rel_type_safe)
        q = f"""
        MATCH (a {{uri: $uri1}}), (b {{uri: $uri2}})
        CREATE (a)-[r:{rel_type_cy} $props]->(b)
        RETURN r, a, b
        """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri1": node1_uri, "uri2": node2_uri, "props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("One of nodes not found, arc not created.")
            r = rec["r"]
            b = rec["b"]
            return self.collect_arc(r, target_node=b)

    def delete_node_by_uri(self, uri: str, detach: bool = True) -> bool:
        """
        delete node by uri. If detach True then detach delete (removes relationships too).
        Returns True if something was deleted.
        """
        if detach:
            q = "MATCH (n {uri:$uri}) DETACH DELETE n RETURN COUNT(n) as cnt"
        else:
            q = "MATCH (n {uri:$uri}) DELETE n RETURN COUNT(n) as cnt"
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": uri})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def delete_arc_by_element_id(self, arc_eid: str) -> bool:
        q = "MATCH ()-[r]-() WHERE elementId(r) = $rid DELETE r RETURN COUNT(r) as cnt"
        with self._driver.session() as sess:
            res = sess.run(q, {"rid": arc_eid})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def update_node(self, uri: str, props: Dict[str, Any], set_labels: Optional[List[str]] = None, remove_labels: Optional[List[str]] = None) -> Optional[TNode]:
        """
        Update node properties using map merge (n += $props).
        Optionally add/remove labels.
        Returns updated node or None.
        """
        if not props and not set_labels and not remove_labels:
            raise RepositoryError("Nothing to update provided.")
        queries = []
        params = {"uri": uri}
        if props:
            queries.append("SET n += $props")
            params["props"] = props
        if set_labels:
            add_labels = ":" + self.transform_labels(set_labels, separator=':')
            queries.append(f"SET n{add_labels}")
        if remove_labels:
            for lbl in remove_labels:
                lbl_safe = _safe_label(lbl)
                queries.append(f"REMOVE n:{lbl_safe}")
        q = "MATCH (n {uri:$uri})\n" + "\n".join(queries) + "\nRETURN n"
        with self._driver.session() as sess:
            res = sess.run(q, params)
            rec = res.single()
            if not rec:
                return None
            return self.collect_node(rec["n"])

    def run_custom_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute arbitrary Cypher. Returns list of records converted to dicts.
        WARNING: user is responsible for safety of query.
        """
        params = params or {}
        with self._driver.session() as sess:
            res = sess.run(query, params)
            out = []
            for r in res:
                rec = {}
                for k in r.keys():
                    rec[k] = self._convert_value(r[k])
                out.append(rec)
            return out


    def collect_node(self, node_obj) -> TNode:
        """
        Возвращает TNode с единственным идентификатором `id` = element_id (строка).
        Убираем legacy numeric id.
        """
        try:
            eid = node_obj.element_id
        except Exception:
            eid = None
        data = {"id": eid}


        try:
            for k in node_obj.keys():
                data[k] = self._convert_value(node_obj[k])
        except Exception:
            try:
                for k, v in dict(node_obj).items():
                    data[k] = self._convert_value(v)
            except Exception:
                pass

        data.setdefault("uri", data.get("uri", None))
        data.setdefault("title", data.get("title", None))
        data.setdefault("description", data.get("description", None))
        return data

    def collect_arc(self, rel_obj, target_node=None) -> TArc:
        """
        Transforms a neo4j.types.graph.Relationship into TArc dict.
        If target_node provided, attempt to read its uri for node_uri_to.
        """
        try:
            eid = rel_obj.element_id
        except Exception:
            eid = None

        rel_type = getattr(rel_obj, "type", None) or type(rel_obj).__name__

        props = {}
        try:
            for k in rel_obj.keys():
                props[k] = self._convert_value(rel_obj[k])
        except Exception:
            pass

        node_from_uri = None
        node_to_uri = None
        try:
            sn = rel_obj.start_node
            en = rel_obj.end_node
            node_from_uri = sn.get("uri", None)
            node_to_uri = en.get("uri", None)
        except Exception:
            if target_node is not None:
                node_to_uri = target_node.get("uri", None)

        arc = {
            "id": eid,
            "uri": rel_type,
            "node_uri_from": node_from_uri,
            "node_uri_to": node_to_uri,
        }
        if props:
            arc["props"] = props
        return arc

    def _convert_value(self, v):
        # Convert neo4j types to python simple types if needed
        # e.g., DateTime, Node, Relationship etc. For simplicity, we convert
        # nodes/relationships to ids or dicts.
        # If something complex, fallback to str()
        try:
            from neo4j.time import DateTime, Date, Time, Duration
            if isinstance(v, (DateTime, Date, Time, Duration)):
                return str(v)
        except Exception:
            pass
        try:
            if hasattr(v, "id") and hasattr(v, "keys"):
                return self.collect_node(v)
        except Exception:
            pass
        try:
            if hasattr(v, "type") and hasattr(v, "start_node"):
                return self.collect_arc(v)
        except Exception:
            pass
        if isinstance(v, dict):
            return {kk: self._convert_value(vv) for kk, vv in v.items()}
        if isinstance(v, list) or isinstance(v, tuple):
            return [self._convert_value(x) for x in v]
        return v


if __name__ == "__main__":
    import os
    import dotenv
    dotenv.load_dotenv()
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USER")
    NEO4J_PASS = os.getenv("NEO4J_PASSWORD")

    repo = Neo4jRepository(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    try:
        print("Creating two test nodes...")
        a = repo.create_node({"title": "Node A", "description": "First", "uri": "node-a-001"}, labels=["Test"])
        b = repo.create_node({"title": "Node B", "description": "Second", "uri": "node-b-001"}, labels=["Test"])
        print("A:", a)
        print("B:", b)

        print("Creating an arc from A to B ...")
        arc = repo.create_arc("node-a-001", "node-b-001", rel_type="LINKS", props={"weight": 3})
        print("Arc created:", arc)

        print("Get all nodes and arcs:")
        all_na = repo.get_all_nodes_and_arcs()
        print(json.dumps(all_na, indent=2, ensure_ascii=False))

        print("Update node A:")
        updated = repo.update_node("node-a-001", {"description": "Updated desc"}, set_labels=["UpdatedLabel"])
        print("Updated:", updated)

        print("Run custom query (count):")
        res = repo.run_custom_query("MATCH (n:Test) RETURN count(n) as cnt")
        print(res)

        print("Cleanup: delete arc by element_id and nodes")
        if isinstance(arc.get("id"), str) and arc.get("id"):
            repo.delete_arc_by_element_id(arc["id"])
        repo.delete_node_by_uri("node-a-001")
        repo.delete_node_by_uri("node-b-001")
    finally:
        repo.close()