
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
    REL_INSTANCE_OF = "INSTANCE_OF"  # (obj)-[:INSTANCE_OF]->(class)

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
            params["uri"] = self.generate_random_string()
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

    def get_ontology(self) -> Dict[str, Any]:
        """
        Возвращает общую структуру онтологии: все классы с их signature и родительскими отношениями.
        """
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
                # Добавим signature
                node["signature"] = self.collect_signature(node.get("uri"))
                out.append(node)
        return {"classes": out}

    def get_ontology_parent_classes(self) -> List[TNode]:
        """
        Классы, у которых нет родителей (top-level classes).
        """
        q = f"""
         MATCH (c:{self.CLASS_LABEL})
         WHERE NOT (c)-[:{self.REL_SUBCLASS}]->(:{self.CLASS_LABEL})
         RETURN c
         """
        with self._driver.session() as sess:
            res = sess.run(q)
            return [self.collect_node(r["c"]) for r in res]

    def get_class(self, class_uri: str) -> Optional[Dict[str, Any]]:
        """
        Получить класс и его signature.
        """
        q = f"MATCH (c:{self.CLASS_LABEL} {{uri:$uri}}) RETURN c LIMIT 1"
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": class_uri})
            rec = res.single()
            if not rec:
                return None
            node = self.collect_node(rec["c"])
            node["signature"] = self.collect_signature(class_uri)
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
        """
        Получить объекты данного класса.
        Поддерживаем как связи (INSTANCE_OF), так и свойство class_uri на ноде.
        """
        q = f"""
         MATCH (o:{self.OBJECT_LABEL})
         OPTIONAL MATCH (o)-[:{self.REL_INSTANCE_OF}]->(c:{self.CLASS_LABEL})
         WHERE (o.{'class_uri'} = $uri) OR (c.uri = $uri)
         RETURN DISTINCT o
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": class_uri})
            return [self.collect_node(r["o"]) for r in res]

    def update_class(self, uri: str, title: Optional[str] = None, description: Optional[str] = None) -> Optional[TNode]:
        """
        Обновить свойства класса (title, description).
        """
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

    def create_class(self, uri: Optional[str] = None, title: Optional[str] = None, description: Optional[str] = None,
                     parent_uri: Optional[str] = None) -> TNode:
        """
        Создать класс. Если parent_uri указан — создаём связь child -[:SUBCLASS_OF]-> parent.
        """
        if not uri:
            uri = self.generate_random_string()
        props = {"uri": uri}
        if title is not None:
            props["title"] = title
        if description is not None:
            props["description"] = description
        q = f"CREATE (c:{self.CLASS_LABEL} $props) RETURN c"
        with self._driver.session() as sess:
            res = sess.run(q, {"props": props})
            rec = res.single()
            node = self.collect_node(rec["c"])
            if parent_uri:
                # создаём связь
                q_rel = f"""
                 MATCH (child:{self.CLASS_LABEL} {{uri:$child_uri}}), (parent:{self.CLASS_LABEL} {{uri:$parent_uri}})
                 CREATE (child)-[:{self.REL_SUBCLASS}]->(parent)
                 RETURN child, parent
                 """
                sess.run(q_rel, {"child_uri": uri, "parent_uri": parent_uri})
            node["signature"] = self.collect_signature(uri)
            return node

    def delete_class(self, uri: str) -> bool:
        """
        Удалить класс и всех его детей (рекурсивно), объекты и всё связанное.
        Подход: найти все ноды descendants, где descendant-[:SUBCLASS_OF*]->(class) (т.е. descendant является самим классом или его потомком),
        и сделать DETACH DELETE для них, а также удалить свойства (DatatypeProperty,ObjectProperty) привязанные только к этим классам.
        """
        with self._driver.session() as sess:
            q_desc = f"""
             MATCH (c:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (d:{self.CLASS_LABEL})
             WHERE (d)-[:{self.REL_SUBCLASS}*0..]->(c)
             RETURN collect(distinct d.uri) as uris
             """
            res = sess.run(q_desc, {"uri": uri})
            rec = res.single()
            if not rec:
                return False
            uris = rec["uris"] or []
            if not uris:
                return False
            q_del_objs = f"""
             MATCH (o:{self.OBJECT_LABEL})
             WHERE o.class_uri IN $uris
             DETACH DELETE o
             """
            sess.run(q_del_objs, {"uris": uris})
            q_del_classes = f"""
             MATCH (d:{self.CLASS_LABEL})
             WHERE d.uri IN $uris
             DETACH DELETE d
             """
            sess.run(q_del_classes, {"uris": uris})
            q_cleanup_props = f"""
             MATCH (p)
             WHERE (p:{self.DATATYPE_PROPERTY_LABEL} OR p:{self.OBJECT_PROPERTY_LABEL})
             AND NOT ( (p)-[:{self.REL_PROPERTY_DOMAIN}|:{self.REL_PROPERTY_RANGE}]-() )
             DETACH DELETE p
             """
            sess.run(q_cleanup_props)
            return True

    def add_class_attribute(self, class_uri: str, prop_uri: Optional[str] = None, title: Optional[str] = None) -> Dict[
        str, Any]:
        """
        Добавить DatatypeProperty к классу: создаёт (p:DatatypeProperty)-[:PROPERTY_DOMAIN]->(class)
        Если prop_uri не указан — генерируем.
        Возвращает созданный property node dict.
        """
        if not prop_uri:
            prop_uri = self.generate_random_string()
        props = {"uri": prop_uri}
        if title:
            props["title"] = title
        q = f"""
         MATCH (c:{self.CLASS_LABEL} {{uri:$class_uri}})
         CREATE (p:{self.DATATYPE_PROPERTY_LABEL} $props)
         CREATE (p)-[:{self.REL_PROPERTY_DOMAIN}]->(c)
         RETURN p
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"class_uri": class_uri, "props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("Class not found or property creation failed.")
            return self.collect_node(rec["p"])

    def delete_class_attribute(self, prop_uri: str) -> bool:
        """
        Удалить DatatypeProperty (по uri). Удаляет ноду свойства и все связи.
        """
        q = f"""
         MATCH (p:{self.DATATYPE_PROPERTY_LABEL} {{uri:$uri}})
         DETACH DELETE p
         RETURN COUNT(p) as cnt
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": prop_uri})
            rec = res.single()
            return bool(rec and rec["cnt"] and rec["cnt"] > 0)

    def add_class_object_attribute(self, class_uri: str, attr_uri: Optional[str] = None,
                                   attr_title: Optional[str] = None, range_class_uri: Optional[str] = None) -> Dict[
        str, Any]:
        """
        Добавить ObjectProperty: создаёт ноду ObjectProperty и связывает domain -> class и range -> range_class (если указан).
        Возвращает созданную ноду property.
        """
        if not attr_uri:
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
            res = sess.run(q, {"class_uri": class_uri, "props": props})
            rec = res.single()
            if not rec:
                raise RepositoryError("Class not found or object property creation failed.")
            created = self.collect_node(rec["p"])
            if range_class_uri:
                q_range = f"""
                 MATCH (p:{self.OBJECT_PROPERTY_LABEL} {{uri:$p_uri}}), (r:{self.CLASS_LABEL} {{uri:$range_uri}})
                 CREATE (p)-[:{self.REL_PROPERTY_RANGE}]->(r)
                 """
                sess.run(q_range, {"p_uri": attr_uri, "range_uri": range_class_uri})
            return created

    def delete_class_object_attribute(self, object_property_uri: str) -> bool:
        """
        Удаление ObjectProperty: удаляем реальные рёбра между объектами, которые имели тип свойства,
        затем удаляем ноду свойства.
        """
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

    def add_class_parent(self, parent_uri: str, target_uri: str) -> bool:
        """
        Присоединить родителя к существующему классу: создаёт (child)-[:SUBCLASS_OF]->(parent)
        target_uri = uri класса-ребёнка, parent_uri = uri родителя
        """
        q = f"""
         MATCH (child:{self.CLASS_LABEL} {{uri:$child_uri}}), (parent:{self.CLASS_LABEL} {{uri:$parent_uri}})
         MERGE (child)-[:{self.REL_SUBCLASS}]->(parent)
         RETURN child, parent
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"child_uri": target_uri, "parent_uri": parent_uri})
            rec = res.single()
            return bool(rec)

    def get_object(self, obj_uri: str) -> Optional[TNode]:
        q = f"""
         MATCH (o:{self.OBJECT_LABEL} {{uri:$uri}})
         OPTIONAL MATCH (o)-[:{self.REL_INSTANCE_OF}]->(c:{self.CLASS_LABEL})
         RETURN o, c
         LIMIT 1
         """
        with self._driver.session() as sess:
            res = sess.run(q, {"uri": obj_uri})
            rec = res.single()
            if not rec:
                return None
            node = self.collect_node(rec["o"])
            if rec.get("c"):
                node["class"] = self.collect_node(rec["c"])
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

    def create_object(self, class_uri: str, obj_uri: Optional[str] = None, title: Optional[str] = None,
                      description: Optional[str] = None, datatype_props: Optional[Dict[str, Any]] = None,
                      object_relations: Optional[List[Dict[str, Any]]] = None) -> TNode:
        """
        Создать объект заданного класса.
        datatype_props: map { field_name: value } - применяются как свойства ноды
        object_relations: список dict с полями:
            { "prop_uri": "...", "target_uri": "...", "direction": 1|-1 }
        where direction == 1 => (this_obj)-[:PROP]->(target)
              direction == -1 => (target)-[:PROP]->(this_obj)
        """
        if not obj_uri:
            obj_uri = self.generate_random_string()
        props = {"uri": obj_uri, "class_uri": class_uri}
        if title:
            props["title"] = title
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
            if object_relations:
                for rel in object_relations:
                    prop_uri = rel.get("prop_uri")
                    target_uri = rel.get("target_uri")
                    direction = rel.get("direction", 1)
                    if not prop_uri or not target_uri:
                        continue
                    rel_label = _safe_label(prop_uri)
                    if direction == 1:
                        q_rel = f"""
                         MATCH (a:{self.OBJECT_LABEL} {{uri:$a_uri}}), (b:{self.OBJECT_LABEL} {{uri:$b_uri}})
                         CREATE (a)-[r:{rel_label}]->(b)
                         RETURN r
                         """
                        sess.run(q_rel, {"a_uri": obj_uri, "b_uri": target_uri})
                    else:
                        q_rel = f"""
                         MATCH (a:{self.OBJECT_LABEL} {{uri:$a_uri}}), (b:{self.OBJECT_LABEL} {{uri:$b_uri}})
                         CREATE (b)-[r:{rel_label}]->(a)
                         RETURN r
                         """
                        sess.run(q_rel, {"a_uri": obj_uri, "b_uri": target_uri})
            return created

    def update_object(self, obj_uri: str, title: Optional[str] = None, description: Optional[str] = None,
                      datatype_props: Optional[Dict[str, Any]] = None,
                      object_relations_to_add: Optional[List[Dict[str, Any]]] = None,
                      object_relations_to_remove: Optional[List[Dict[str, Any]]] = None) -> Optional[TNode]:
        """
        Обновить объект: менять свойства (datatype_props), title/description, добавлять/удалять object relations.
        object_relations_... формат как в create_object.
        """
        set_parts = {}
        if title is not None:
            set_parts["title"] = title
        if description is not None:
            set_parts["description"] = description
        if datatype_props:
            for k, v in datatype_props.items():
                set_parts[k] = v
        if not set_parts and not object_relations_to_add and not object_relations_to_remove:
            raise RepositoryError("Nothing to update for object.")
        params = {"uri": obj_uri}
        with self._driver.session() as sess:
            if set_parts:
                q = f"""
                 MATCH (o:{self.OBJECT_LABEL} {{uri:$uri}})
                 SET o += $props
                 RETURN o
                 """
                res = sess.run(q, {"uri": obj_uri, "props": set_parts})
                rec = res.single()
            else:
                q = f"MATCH (o:{self.OBJECT_LABEL} {{uri:$uri}}) RETURN o"
                res = sess.run(q, {"uri": obj_uri})
                rec = res.single()
            if not rec:
                return None
            node = self.collect_node(rec["o"])
            if object_relations_to_remove:
                for rel in object_relations_to_remove:
                    prop_uri = rel.get("prop_uri")
                    target_uri = rel.get("target_uri")
                    direction = rel.get("direction", 1)
                    if not prop_uri or not target_uri:
                        continue
                    rel_label = _safe_label(prop_uri)
                    if direction == 1:
                        q_del = f"""
                         MATCH (a:{self.OBJECT_LABEL} {{uri:$a_uri}})-[r:{rel_label}]->(b:{self.OBJECT_LABEL} {{uri:$b_uri}})
                         DELETE r
                         """
                        sess.run(q_del, {"a_uri": obj_uri, "b_uri": target_uri})
                    else:
                        q_del = f"""
                         MATCH (b:{self.OBJECT_LABEL} {{uri:$b_uri}})-[r:{rel_label}]->(a:{self.OBJECT_LABEL} {{uri:$a_uri}})
                         DELETE r
                         """
                        sess.run(q_del, {"a_uri": obj_uri, "b_uri": target_uri})
            if object_relations_to_add:
                for rel in object_relations_to_add:
                    prop_uri = rel.get("prop_uri")
                    target_uri = rel.get("target_uri")
                    direction = rel.get("direction", 1)
                    if not prop_uri or not target_uri:
                        continue
                    rel_label = _safe_label(prop_uri)
                    if direction == 1:
                        q_add = f"""
                         MATCH (a:{self.OBJECT_LABEL} {{uri:$a_uri}}), (b:{self.OBJECT_LABEL} {{uri:$b_uri}})
                         MERGE (a)-[r:{rel_label}]->(b)
                         RETURN r
                         """
                        sess.run(q_add, {"a_uri": obj_uri, "b_uri": target_uri})
                    else:
                        q_add = f"""
                         MATCH (a:{self.OBJECT_LABEL} {{uri:$a_uri}}), (b:{self.OBJECT_LABEL} {{uri:$b_uri}})
                         MERGE (b)-[r:{rel_label}]->(a)
                         RETURN r
                         """
                        sess.run(q_add, {"a_uri": obj_uri, "b_uri": target_uri})
            return self.get_object(obj_uri)

    def collect_signature(self, class_uri: str) -> Dict[str, Any]:
        """
        Собрать signature для класса: datatype properties (params) и object properties (obj_params).
        Отбираем свойства, которые:
         - напрямую имеют domain == класс (p)-[:PROPERTY_DOMAIN]->(class)
         - либо привязаны к классам, которые находятся по цепочке наследования (descendants OR ancestors в
         зависимости от вашей онтологии)
        Для простоты: используем поиск свойств, у которых (p)-[:PROPERTY_DOMAIN]->(some_class),
        и some_class является либо самим классом, либо классом, связанным SUBCLASS_OF* с ним (в обе стороны).
        """
        params = []
        obj_params = []

        with self._driver.session() as sess:
            # DatatypeProperties: найдём все p, где p-[:PROPERTY_DOMAIN]->(s)
            q_dt = f"""
             MATCH (s:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (p:{self.DATATYPE_PROPERTY_LABEL})-[:{self.REL_PROPERTY_DOMAIN}]->(s)
             RETURN DISTINCT p
             """
            res_dt = sess.run(q_dt, {"uri": class_uri})
            for r in res_dt:
                p = self.collect_node(r["p"])
                params.append({"title": p.get("title"), "url": p.get("uri")})
            # domain from classes that are subclass of s (их свойства наследуются вверх?) — включим поля от подклассов тоже
            q_dt_inherited = f"""
             MATCH (s:{self.CLASS_LABEL} {{uri:$uri}})
             MATCH (x:{self.CLASS_LABEL})-[:{self.REL_SUBCLASS}*]->(s)
             MATCH (p:{self.DATATYPE_PROPERTY_LABEL})-[:{self.REL_PROPERTY_DOMAIN}]->(x)
             RETURN DISTINCT p
             """
            res_dt2 = sess.run(q_dt_inherited, {"uri": class_uri})
            for r in res_dt2:
                p = self.collect_node(r["p"])
                entry = {"title": p.get("title"), "url": p.get("uri")}
                if entry not in params:
                    params.append(entry)

            # ObjectProperties  direction 1 (from this class to target range), -1 (from external class to this class)
            # direction == 1: (p)-[:PROPERTY_DOMAIN]->(this_class) and (p)-[:PROPERTY_RANGE]->(rclass)
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

            #  direction == -1: (p)-[:PROPERTY_RANGE]->(this_class) and (p)-[:PROPERTY_DOMAIN]->(other_class)
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
        print("\n=== Ontology Test (Class / Properties) ===")

        # Create two classes
        cls_person = repo.create_node(
            {"title": "Person", "description": "Human being", "uri": "class-person-001"},
            labels=["Class"]
        )
        cls_book = repo.create_node(
            {"title": "Book", "description": "A written work", "uri": "class-book-001"},
            labels=["Class"]
        )
        print("Created classes:")
        print("Person:", cls_person)
        print("Book:", cls_book)

        # Add parent relationship (Book inherits from Person, for example)
        repo.create_arc("class-book-001", "class-person-001", rel_type="PARENT")

        # Create DatatypeProperty for Person (e.g., "age")
        dt_age = repo.create_node(
            {"title": "age", "description": "Person's age", "uri": "prop-age-001"},
            labels=["DatatypeProperty"]
        )
        repo.create_arc("class-person-001", "prop-age-001", rel_type="HAS_DATATYPE")

        # Create ObjectProperty (Person -> Book)
        op_writes = repo.create_node(
            {"title": "writes", "description": "Person writes Book", "uri": "prop-writes-001"},
            labels=["ObjectProperty"]
        )
        repo.create_arc("class-person-001", "prop-writes-001", rel_type="HAS_PROPERTY")
        repo.create_arc("prop-writes-001", "class-book-001", rel_type="RANGE")

        # View full ontology
        ontology = repo.get_all_nodes_and_arcs()
        print("\nOntology (nodes + arcs):")
        print(json.dumps(ontology, indent=2, ensure_ascii=False))

        # Update class Person
        updated_cls = repo.update_node("class-person-001", {"description": "Updated Person description"})
        print("\nUpdated Person class:")
        print(updated_cls)

        # Cleanup
        print("\nCleaning up ontology...")
        repo.delete_node_by_uri("class-person-001")
        repo.delete_node_by_uri("class-book-001")
        repo.delete_node_by_uri("prop-age-001")
        repo.delete_node_by_uri("prop-writes-001")

    finally:
        repo.close()