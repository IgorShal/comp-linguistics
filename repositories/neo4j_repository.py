import json
import uuid
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase, Driver

from utils.helpers import _safe_label, TNode, TArc, _LABEL_RE
from utils.repository_error import RepositoryError


class Neo4jRepository:
    CLASS_LABEL = "Class"
    OBJECT_LABEL = "Object"
    DATATYPE_PROPERTY_LABEL = "DatatypeProperty"
    OBJECT_PROPERTY_LABEL = "ObjectProperty"

    REL_SUBCLASS = "SUBCLASS_OF"  # child -[:SUBCLASS_OF]-> parent
    REL_PROPERTY_DOMAIN = "PROPERTY_DOMAIN"  # (prop)-[:PROPERTY_DOMAIN]->(class)
    REL_PROPERTY_RANGE = "PROPERTY_RANGE"  # (prop)-[:PROPERTY_RANGE]->(class)
    REL_INSTANCE_OF = "TYPE"  # (obj)-[:TYPE]->(class)

    def __init__(self, uri: str, user: str, password: str, encrypted: bool = False):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password), encrypted=encrypted)

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

    # ------------------ Helper lookups ------------------
    def _find_node_uri_by_title(self, label: Optional[str], title: str) -> Optional[str]:
        """Find first node.uri by label and title. If label is None matches any label with property title."""
        label_cy = f":{_safe_label(label)}" if label else ""
        q = f"MATCH (n{label_cy} {{title:$title}}) RETURN n.uri as uri LIMIT 1"
        with self._driver.session() as sess:
            rec = sess.run(q, {"title": title}).single()
            if not rec:
                return None
            return rec.get("uri")

    def _find_node_by_title(self, label: Optional[str], title: str) -> Optional[TNode]:
        uri = self._find_node_uri_by_title(label, title)
        if not uri:
            return None
        return self.get_node_by_uri(uri)

    # ------------------ Basic node operations (uris are always generated) ------------------
    def create_node(self, params: Dict[str, Any], labels: Optional[List[str]] = None) -> TNode:
        """
        Always creates a fresh node with a generated `uri` (user-provided uri is ignored).
        `params` may include title/description and any other props.
        """
        props = dict(params or {})
        props.pop("uri", None)  # ignore provided uri
        props["uri"] = self.generate_random_string()
        labels_cy = ":" + self.transform_labels(labels, separator=':') if labels else ""
        q = f"CREATE (n{labels_cy} $props) RETURN n"
        with self._driver.session() as sess:
            res = sess.run(q, {"props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("Node creation failed.")
            return self.collect_node(rec["n"])

    def create_arc(self, node1_uri: str, node2_uri: str, rel_type: str = "RELATED",
                   props: Optional[Dict[str, Any]] = None) -> TArc:
        """
        Create directed arc (node1)-[r:RELTYPE {props}]->(node2).
        rel_type will be validated (only letters/numbers/_ allowed).
        Returns created arc dict.
        """
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

    def create_arc_by_titles(self, node1_title: str, node2_title: str, rel_type: str = "RELATED",
                             label1: Optional[str] = None, label2: Optional[str] = None,
                             props: Optional[Dict[str, Any]] = None) -> TArc:
        """
        Convenience: find nodes by title (optionally restrict by label) and create arc between them.
        Titles must be unique or first match will be used.
        """
        uri1 = self._find_node_uri_by_title(label1, node1_title)
        uri2 = self._find_node_uri_by_title(label2, node2_title)
        if not uri1 or not uri2:
            raise RepositoryError("One of nodes not found by title, arc not created.")
        return self.create_arc(uri1, uri2, rel_type=rel_type, props=props)

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
        q = f"""
          MATCH (n)
          OPTIONAL MATCH (n)-[r]->(m)
          WITH n, collect(DISTINCT {{r: r, m: m}}) as arcs
          RETURN n, arcs
        """
        with self._driver.session() as sess:
            res = sess.run(q)
            out = []
            for r in res:
                n = r["n"]
                arcs_entries = r["arcs"] or []
                node_dict = self.collect_node(n)
                arcs_list = []
                for entry in arcs_entries:
                    rel = entry.get("r")
                    target = entry.get("m")
                    if rel is None:
                        continue
                    arc = self.collect_arc(rel, target_node=target)
                    arcs_list.append(arc)
                if arcs_list:
                    node_dict["arcs"] = arcs_list
                out.append(node_dict)
            return out

    def get_nodes_by_labels(self, labels: List[str]) -> List[TNode]:
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

    def get_node_by_title(self, label: Optional[str], title: str) -> Optional[TNode]:
        return self._find_node_by_title(label, title)

    # ------------------ Delete / Update (unchanged behaviour expects uri) ------------------
    def delete_node_by_uri(self, uri: str, detach: bool = True) -> bool:
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

    def update_node(self, uri: str, props: Dict[str, Any], set_labels: Optional[List[str]] = None,
                    remove_labels: Optional[List[str]] = None) -> Optional[TNode]:
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

    # ------------------ Ontology helpers ------------------
    def get_ontology(self) -> Dict[str, Any]:
        q = f"""
         MATCH (c:{self.CLASS_LABEL})
         OPTIONAL MATCH (c)-[:{self.REL_SUBCLASS}]->(p:{self.CLASS_LABEL})
         RETURN c, collect(distinct p.uri) as parents
         """
        out = []
        with self._driver.session() as sess:
            res = sess.run(q)
            for r in res:
                node = self.collect_node(r["c"])
                node["parents"] = r["parents"]
                node["signature"] = self.collect_signature(node.get("uri"))
                out.append(node)
        return {"classes": out}

    def get_ontology_parent_classes(self) -> List[TNode]:
        q = f"""
         MATCH (c:{self.CLASS_LABEL})
         WHERE NOT (c)-[:{self.REL_SUBCLASS}]->(:{self.CLASS_LABEL})
         RETURN c
         """
        with self._driver.session() as sess:
            res = sess.run(q)
            return [self.collect_node(r["c"]) for r in res]

    # ------------------ Class CRUD (uri always generated on create) ------------------
    def create_class(self, title: str, description: Optional[str] = None, parent_title: Optional[str] = None) -> TNode:
        """
        Create a new class. The node `uri` is always generated internally (user cannot pass uri).
        To attach to a parent, pass parent_title (the existing parent's title). Titles should be unique.
        """
        props = {"uri": self.generate_random_string(), "title": title}
        if description is not None:
            props["description"] = description
        q = f"CREATE (c:{self.CLASS_LABEL} $props) RETURN c"
        with self._driver.session() as sess:
            res = sess.run(q, {"props": props})
            rec = res.single()
            node = self.collect_node(rec["c"])
            if parent_title:
                parent_uri = self._find_node_uri_by_title(self.CLASS_LABEL, parent_title)
                if not parent_uri:
                    raise RepositoryError("Parent class with provided title not found.")
                # create subclass relation
                q_rel = f"MATCH (child:{self.CLASS_LABEL} {{uri:$child_uri}}), (parent:{self.CLASS_LABEL} {{uri:$parent_uri}}) CREATE (child)-[:{self.REL_SUBCLASS}]->(parent)"
                sess.run(q_rel, {"child_uri": node["uri"], "parent_uri": parent_uri})
            node["signature"] = self.collect_signature(node["uri"])
            return node

    def get_class(self, class_uri: str) -> Optional[Dict[str, Any]]:
        q = f"MATCH (c:{self.CLASS_LABEL} {{uri:$uri}}) RETURN c LIMIT 1"
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": class_uri})
            rec = res.single()
            if not rec:
                return None
            node = self.collect_node(rec["c"])
            node["signature"] = self.collect_signature(class_uri)
            return node

    def get_class_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        node = self._find_node_by_title(self.CLASS_LABEL, title)
        if not node:
            return None
        node["signature"] = self.collect_signature(node["uri"])
        return node

    def get_class_parents(self, class_uri: str) -> List[TNode]:
        q = f"""
         MATCH (c:{self.CLASS_LABEL} {{uri:$uri}})-[:{self.REL_SUBCLASS}]->(p:{self.CLASS_LABEL})
         RETURN p
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": class_uri})
            return [self.collect_node(r["p"]) for r in res]

    def get_class_children(self, class_uri: str) -> List[TNode]:
        q = f"""
         MATCH (child:{self.CLASS_LABEL})-[:{self.REL_SUBCLASS}]->(c:{self.CLASS_LABEL} {{uri:$uri}})
         RETURN child
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": class_uri})
            return [self.collect_node(r["child"]) for r in res]

    def get_class_objects(self, class_uri: str) -> List[TNode]:
        q = f"""
        MATCH (o:{self.OBJECT_LABEL})
        OPTIONAL MATCH (o)-[r]->(c:{self.CLASS_LABEL})
        WHERE (o.class_uri = $uri) OR (r IS NOT NULL AND type(r) = $inst_rel AND c.uri = $uri)
        RETURN DISTINCT o
        """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": class_uri, "inst_rel": self.REL_INSTANCE_OF})
            return [self.collect_node(r["o"]) for r in res]

    def update_class(self, uri: str, title: Optional[str] = None, description: Optional[str] = None) -> Optional[TNode]:
        props = {}
        if title is not None:
            props["title"] = title
        if description is not None:
            props["description"] = description
        if not props:
            raise RepositoryError("Nothing to update for class.")
        q = f"""
         MATCH (c:{self.CLASS_LABEL} {{uri:$uri}})
         SET c += $props
         RETURN c
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": uri, "props": props})
            rec = res.single()
            if not rec:
                return None
            node = self.collect_node(rec["c"])
            node["signature"] = self.collect_signature(uri)
            return node

    def delete_class(self, uri: str) -> bool:
        # unchanged behaviour: deletion by uri
        with self._driver.session() as sess:
            q_uris = f"""
            MATCH (c:{self.CLASS_LABEL} {{uri:$uri}})
            OPTIONAL MATCH (d:{self.CLASS_LABEL})
            WHERE (d)-[:{self.REL_SUBCLASS}*0..]->(c)
            RETURN collect(distinct d.uri) as uris
            """
            res = sess.run(q_uris, {"uri": uri})
            rec = res.single()
            if not rec:
                return False
            uris = [u for u in (rec["uris"] or []) if u]
            if not uris:
                return False

            q_del_by_field = f"""
            MATCH (o:{self.OBJECT_LABEL})
            WHERE o.class_uri IN $uris
            DETACH DELETE o
            """
            sess.run(q_del_by_field, {"uris": uris})

            q_del_by_rel = f"""
            MATCH (o:{self.OBJECT_LABEL})-[r:{self.REL_INSTANCE_OF}]->(c:{self.CLASS_LABEL})
            WHERE c.uri IN $uris
            DETACH DELETE o
            """
            sess.run(q_del_by_rel, {"uris": uris})

            q_del_props_domain = f"""
            MATCH (p)-[:{self.REL_PROPERTY_DOMAIN}]->(c:{self.CLASS_LABEL})
            WHERE c.uri IN $uris
            DETACH DELETE p
            """
            sess.run(q_del_props_domain, {"uris": uris})

            q_del_props_range = f"""
            MATCH (p)-[:{self.REL_PROPERTY_RANGE}]->(c:{self.CLASS_LABEL})
            WHERE c.uri IN $uris
            DETACH DELETE p
            """
            sess.run(q_del_props_range, {"uris": uris})

            q_del_classes = f"""
            MATCH (d:{self.CLASS_LABEL})
            WHERE d.uri IN $uris
            DETACH DELETE d
            """
            sess.run(q_del_classes, {"uris": uris})

            return True

    # ------------------ Class attributes ------------------
    def add_class_attribute(self, class_title: str, prop_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a DATATYPE property node and link it to class identified by class_title.
        Property uri is generated internally. Returns created property node.
        """
        class_node = self._find_node_by_title(self.CLASS_LABEL, class_title)
        if not class_node:
            raise RepositoryError("Class with provided title not found.")
        prop_uri = self.generate_random_string()
        props = {"uri": prop_uri}
        if prop_title:
            props["title"] = prop_title
        q = f"""
         MATCH (c:{self.CLASS_LABEL} {{uri:$class_uri}})
         CREATE (p:{self.DATATYPE_PROPERTY_LABEL} $props)
         CREATE (p)-[:{self.REL_PROPERTY_DOMAIN}]->(c)
         RETURN p
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"class_uri": class_node["uri"], "props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("Class not found or property creation failed.")
            return self.collect_node(rec["p"])

    def delete_class_attribute(self, prop_uri: str) -> bool:
        q = f"""
         MATCH (p:{self.DATATYPE_PROPERTY_LABEL} {{uri:$uri}})
         DETACH DELETE p
         RETURN COUNT(p) as cnt
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": prop_uri})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def add_class_object_attribute(self, class_title: str, attr_title: Optional[str] = None,
                                   range_class_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Create an OBJECT property linked to class identified by class_title. Range may be provided by range_class_title.
        Property uri is generated internally.
        """
        class_node = self._find_node_by_title(self.CLASS_LABEL, class_title)
        if not class_node:
            raise RepositoryError("Class with provided title not found.")
        attr_uri = self.generate_random_string()
        props = {"uri": attr_uri}
        if attr_title:
            props["title"] = attr_title
        q = f"""
         MATCH (c:{self.CLASS_LABEL} {{uri:$class_uri}})
         CREATE (p:{self.OBJECT_PROPERTY_LABEL} $props)
         CREATE (p)-[:{self.REL_PROPERTY_DOMAIN}]->(c)
         RETURN p
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"class_uri": class_node["uri"], "props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("Class not found or object property creation failed.")
            created = self.collect_node(rec["p"])
            if range_class_title:
                range_node = self._find_node_by_title(self.CLASS_LABEL, range_class_title)
                if not range_node:
                    raise RepositoryError("Range class with provided title not found.")
                q_range = f"""
                 MATCH (p:{self.OBJECT_PROPERTY_LABEL} {{uri:$p_uri}}), (r:{self.CLASS_LABEL} {{uri:$range_uri}})
                 CREATE (p)-[:{self.REL_PROPERTY_RANGE}]->(r)
                 """
                sess.run(q_range, {"p_uri": attr_uri, "range_uri": range_node["uri"]})
            return created

    def delete_class_object_attribute(self, object_property_uri: str) -> bool:
        rel_type_label = _safe_label(object_property_uri)
        with self._driver.session() as sess:
            q_del_rels = f"""
             MATCH ()-[r]-()
             WHERE type(r) = $rel_type
             DELETE r
             """
            sess.run(q_del_rels, {"rel_type": rel_type_label})
            q_del_node = f"""
             MATCH (p:{self.OBJECT_PROPERTY_LABEL} {{uri:$uri}})
             DETACH DELETE p
             RETURN COUNT(p) as cnt
             """
            res = sess.run(q_del_node, {"uri": object_property_uri})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def add_class_parent(self, parent_title: str, target_title: str) -> bool:
        try:
            uri_parent = self._find_node_uri_by_title(self.CLASS_LABEL, parent_title)
            uri_target = self._find_node_uri_by_title(self.CLASS_LABEL, target_title)
            if not uri_parent or not uri_target:
                return False
            self.create_arc(uri_target, uri_parent, rel_type=self.REL_SUBCLASS, props=None)
            return True
        except RepositoryError:
            return False

    # ------------------ Object CRUD ------------------
    def get_object(self, obj_uri: str) -> Optional[TNode]:
        node = self.get_node_by_uri(obj_uri)
        if not node:
            return None
        class_info = None
        q = f"""
                MATCH (o {{uri:$uri}})-[:{self.REL_INSTANCE_OF}]->(c:{self.CLASS_LABEL})
                RETURN c LIMIT 1
                """
        with self._driver.session() as sess:
            rec = sess.run(q, {"uri": obj_uri}).single()
            if rec and rec.get("c"):
                class_info = self.collect_node(rec["c"])
        if not class_info and node.get("class_uri"):
            class_info = self.get_node_by_uri(node["class_uri"])
        if class_info:
            node["class"] = class_info
        return node

    def delete_object(self, obj_uri: str) -> bool:
        q = f"""
         MATCH (o:{self.OBJECT_LABEL} {{uri:$uri}})
         DETACH DELETE o
         RETURN COUNT(o) as cnt
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": obj_uri})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def create_object(self, class_title: str, obj_title: Optional[str] = None, description: Optional[str] = None,
                      datatype_props: Optional[Dict[str, Any]] = None,
                      obj_params: Optional[List[Dict[str, Any]]] = None) -> TNode:
        """
        Create an object instance for class identified by class_title. Object `uri` is generated internally.
        obj_params is a list of dicts with keys: prop_title (the property title to use as relationship name), target_title, direction (1 default means (this)->(target), -1 means reverse). Titles are used to find property and target nodes.
        """
        class_node = self._find_node_by_title(self.CLASS_LABEL, class_title)
        if not class_node:
            raise RepositoryError("Class with provided title not found.")
        obj_uri = self.generate_random_string()
        props = {"uri": obj_uri, "class_uri": class_node["uri"]}
        if obj_title:
            props["title"] = obj_title
        if description:
            props["description"] = description
        if datatype_props:
            for k, v in datatype_props.items():
                props[k] = v

        q = f"CREATE (o:{self.OBJECT_LABEL} $props) RETURN o"
        with self._driver.session() as sess:
            res = sess.run(q, {"props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("Object creation failed.")
            created = self.collect_node(rec["o"])

            # create TYPE relationship to class
            q_type = f"MATCH (o:{self.OBJECT_LABEL} {{uri:$o_uri}}), (c:{self.CLASS_LABEL} {{uri:$c_uri}}) CREATE (o)-[:{self.REL_INSTANCE_OF}]->(c)"
            sess.run(q_type, {"o_uri": obj_uri, "c_uri": class_node["uri"]})

            # create object relationships
            if obj_params:
                for rel in obj_params:
                    prop_title = rel.get("prop_title")
                    target_title = rel.get("target_title")
                    direction = rel.get("direction", 1)
                    if not prop_title or not target_title:
                        continue
                    prop_node = self._find_node_by_title(self.OBJECT_PROPERTY_LABEL,
                                                         prop_title) or self._find_node_by_title(
                        self.DATATYPE_PROPERTY_LABEL, prop_title)
                    target_node = self._find_node_by_title(None, target_title)
                    if not prop_node or not target_node:
                        continue
                    try:
                        rel_label = prop_node.get("uri")
                        # create arc using uri namesafe
                        if int(direction) == 1:
                            self.create_arc(obj_uri, target_node["uri"], rel_type=rel_label, props=None)
                        else:
                            self.create_arc(target_node["uri"], obj_uri, rel_type=rel_label, props=None)
                    except RepositoryError:
                        pass

        return created

    def update_object(self, obj_uri: str, title: Optional[str] = None, description: Optional[str] = None,
                      datatype_props: Optional[Dict[str, Any]] = None,
                      obj_params_to_add: Optional[List[Dict[str, Any]]] = None,
                      obj_params_to_remove: Optional[List[Dict[str, Any]]] = None) -> Optional[TNode]:
        set_props = {}
        if title is not None:
            set_props["title"] = title
        if description is not None:
            set_props["description"] = description
        if datatype_props:
            for k, v in datatype_props.items():
                set_props[k] = v

        with self._driver.session() as sess:
            if set_props:
                q = f"""
                  MATCH (o:{self.OBJECT_LABEL} {{uri:$uri}})
                  SET o += $props
                  RETURN o
                  """
                res = sess.run(q, {"uri": obj_uri, "props": set_props})
                rec = res.single()
                if not rec:
                    return None

            if obj_params_to_remove:
                for rel in obj_params_to_remove:
                    prop_title = rel.get("prop_title")
                    target_title = rel.get("target_title")
                    direction = rel.get("direction", 1)
                    if not prop_title or not target_title:
                        continue
                    prop_node = self._find_node_by_title(self.OBJECT_PROPERTY_LABEL,
                                                         prop_title) or self._find_node_by_title(
                        self.DATATYPE_PROPERTY_LABEL, prop_title)
                    target_node = self._find_node_by_title(None, target_title)
                    if not prop_node or not target_node:
                        continue
                    rel_label = _safe_label(prop_node.get("uri"))
                    if int(direction) == 1:
                        q_del = f"""
                          MATCH (a:{self.OBJECT_LABEL} {{uri:$a_uri}})-[r:`{rel_label}`]->(b {{uri:$b_uri}})
                          DELETE r
                          """
                        sess.run(q_del, {"a_uri": obj_uri, "b_uri": target_node["uri"]})
                    else:
                        q_del = f"""
                          MATCH (b {{uri:$b_uri}})-[r:`{rel_label}`]->(a:{self.OBJECT_LABEL} {{uri:$a_uri}})
                          DELETE r
                          """
                        sess.run(q_del, {"a_uri": obj_uri, "b_uri": target_node["uri"]})

            if obj_params_to_add:
                for rel in obj_params_to_add:
                    prop_title = rel.get("prop_title")
                    target_title = rel.get("target_title")
                    direction = rel.get("direction", 1)
                    if not prop_title or not target_title:
                        continue
                    prop_node = self._find_node_by_title(self.OBJECT_PROPERTY_LABEL,
                                                         prop_title) or self._find_node_by_title(
                        self.DATATYPE_PROPERTY_LABEL, prop_title)
                    target_node = self._find_node_by_title(None, target_title)
                    if not prop_node or not target_node:
                        continue
                    try:
                        if int(direction) == 1:
                            self.create_arc(obj_uri, target_node["uri"], rel_type=prop_node.get("uri"), props=None)
                        else:
                            self.create_arc(target_node["uri"], obj_uri, rel_type=prop_node.get("uri"), props=None)
                    except RepositoryError:
                        pass

        return self.get_object(obj_uri)

    # ------------------ Signature / Schema discovery ------------------
    def collect_signature(self, class_uri: str) -> Dict[str, Any]:
        params = []
        obj_params = []

        with self._driver.session() as sess:
            q_dt = f"""
             MATCH (s:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (p:{self.DATATYPE_PROPERTY_LABEL})-[:{self.REL_PROPERTY_DOMAIN}]->(s)
             RETURN DISTINCT p
             """
            res_dt = sess.run(q_dt, {"uri": class_uri})
            for r in res_dt:
                p = self.collect_node(r["p"])
                params.append({"title": p.get("title"), "url": p.get("uri")})

            q_dt_inherited = f"""
             MATCH (s:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (x:{self.CLASS_LABEL})
             WHERE (s)-[:{self.REL_SUBCLASS}*]->(x)
             MATCH (p:{self.DATATYPE_PROPERTY_LABEL})-[:{self.REL_PROPERTY_DOMAIN}]->(x)
             RETURN DISTINCT p
             """
            res_dt2 = sess.run(q_dt_inherited, {"uri": class_uri})
            for r in res_dt2:
                p = self.collect_node(r["p"])
                entry = {"title": p.get("title"), "url": p.get("uri")}
                if entry not in params:
                    params.append(entry)

            q_obj_forward = f"""
             MATCH (s:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (p:{self.OBJECT_PROPERTY_LABEL})-[:{self.REL_PROPERTY_DOMAIN}]->(s)
             OPTIONAL MATCH (p)-[:{self.REL_PROPERTY_RANGE}]->(r:{self.CLASS_LABEL})
             RETURN DISTINCT p, r
             """
            res_obj_f = sess.run(q_obj_forward, {"uri": class_uri})
            for r in res_obj_f:
                p = self.collect_node(r["p"])
                rcls = self.collect_node(r["r"]) if r.get("r") else None
                obj_params.append({
                    "title": p.get("title"),
                    "url": p.get("uri"),
                    "target_class_url": rcls.get("uri") if rcls else None,
                    "relation_direction": 1
                })
            q_obj_backward = f"""
             MATCH (s:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (p:{self.OBJECT_PROPERTY_LABEL})-[:{self.REL_PROPERTY_RANGE}]->(s)
             OPTIONAL MATCH (p)-[:{self.REL_PROPERTY_DOMAIN}]->(r:{self.CLASS_LABEL})
             RETURN DISTINCT p, r
             """
            res_obj_b = sess.run(q_obj_backward, {"uri": class_uri})
            for r in res_obj_b:
                p = self.collect_node(r["p"])
                rcls = self.collect_node(r["r"]) if r.get("r") else None
                obj_params.append({
                    "title": p.get("title"),
                    "url": p.get("uri"),
                    "target_class_url": rcls.get("uri") if rcls else None,
                    "relation_direction": -1
                })

        return {"params": params, "obj_params": obj_params}

    # ------------------ Conversion helpers ------------------
    def _convert_value(self, v):
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

    def collect_node(self, node_obj) -> TNode:
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

    def delete_arc_by_id(self, arc_id: str) -> bool:
        """
        Delete a relationship (arc) by its internal Neo4j id(r).
        Returns True if something was deleted, False otherwise.
        """
        q = "MATCH ()-[r]-() WHERE id(r) = $rid DELETE r RETURN COUNT(r) as cnt"
        with self._driver.session() as sess:
            res = sess.run(q, {"rid": int(arc_id)})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def run_custom_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Run an arbitrary Cypher query and return a list of dicts with converted values.
        This should only be used for read/debug operations — use parameterized Cypher for writes.
        """
        with self._driver.session() as sess:
            try:
                res = sess.run(query)
                records = []
                for r in res:
                    rec_dict = {}
                    for k in r.keys():
                        rec_dict[k] = self._convert_value(r[k])
                    records.append(rec_dict)
                return records
            except Exception as e:
                raise RepositoryError(f"Error running custom query: {e}")


# End of file


if __name__ == "__main__":
    import os
    import json
    import dotenv

    dotenv.load_dotenv()
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USER")
    NEO4J_PASS = os.getenv("NEO4J_PASSWORD")

    repo = Neo4jRepository(NEO4J_URI, NEO4J_USER, NEO4J_PASS)

    try:
        repo.run_custom_query("MATCH (n) DETACH DELETE n")
        print("\n=== DEMO: Complex ontology for collect_node ===")

        # === Создание классов ===
        person = repo.create_class(title="Person", description="Human being")
        employee = repo.create_class(title="Employee", description="Employee of company", parent_title="Person")
        manager = repo.create_class(title="Manager", description="Manages employees", parent_title="Employee")
        project = repo.create_class(title="Project", description="Project entity")

        print("Classes created:", person["uri"], employee["uri"], manager["uri"], project["uri"])

        p_name = repo.add_class_attribute(class_title="Person", prop_title="name")
        p_age = repo.add_class_attribute(class_title="Person", prop_title="age")
        e_salary = repo.add_class_attribute(class_title="Employee", prop_title="salary")

        # === Object Properties ===
        op_manager_of = repo.add_class_object_attribute(
            class_title="Manager",
            attr_title="managerOf",
            range_class_title="Employee"
        )
        op_works_on = repo.add_class_object_attribute(
            class_title="Employee",
            attr_title="worksOn",
            range_class_title="Project"
        )

        alice = repo.create_object(
            class_title="Manager",
            obj_title="Alice",
            datatype_props={"name": "Alice", "age": 42}
        )
        bob = repo.create_object(
            class_title="Employee",
            obj_title="Bob",
            datatype_props={"name": "Bob", "age": 30, "salary": 70000}
        )
        carol = repo.create_object(
            class_title="Employee",
            obj_title="Carol",
            datatype_props={"name": "Carol", "age": 28, "salary": 65000}
        )
        projx = repo.create_object(
            class_title="Project",
            obj_title="Project X"
        )

        mgr_node = repo.get_node_by_title("Class", "Manager")
        print("\nCollected node for Class:Manager (collect_node output):")
        print(json.dumps(mgr_node, indent=2, ensure_ascii=False))

        print("\nCollect signature for Class:Manager (params + obj_params):")
        sig_mgr = repo.collect_signature(repo.get_class_by_title("Manager")["uri"])
        print(json.dumps(sig_mgr, indent=2, ensure_ascii=False))

        all_nodes_and_arcs = repo.get_all_nodes_and_arcs()
        print("\nSample of get_all_nodes_and_arcs (show first 6 nodes):")
        print(json.dumps(all_nodes_and_arcs[:6], indent=2, ensure_ascii=False))

        alice_node = repo.get_node_by_title("Object", "Alice")
        print("\nCollected node for Alice (object instance):")
        print(json.dumps(alice_node, indent=2, ensure_ascii=False))

        print(repo.collect_signature(alice_node["uri"]))


    finally:
        repo.close()
