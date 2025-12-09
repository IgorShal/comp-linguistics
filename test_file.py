import json
import os
import re
from typing import Dict, List, Any

import dotenv

from repositories.neo4j_repository import Neo4jRepository

dotenv.load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")

with open("graph (2).json", 'r', encoding='utf-8') as f:
    dictionarty = json.loads(f.read())



import re
import json
from typing import List, Dict, Any

def _extract_label(data: Dict[str, Any]) -> str:
    lbl_keys = [
        "http://www.w3.org/2000/01/rdf-schema#label",
        "rdfs:label", "label", "title"
    ]
    for k in lbl_keys:
        if k in data:
            v = data[k]
            if isinstance(v, list) and v:
                return v[0]
            elif isinstance(v, str):
                return v
    return data.get("title") or data.get("id") or ""

def _sanitize_rel_type(uri: str) -> str:
    if not uri:
        return "RELATED"
    frag = re.split(r"[#/]", uri)[-1]
    s = re.sub(r"[^0-9A-Za-z_]", "_", frag)
    if not s:
        return "RELATED"
    if re.match(r"^[0-9]", s):
        s = "R_" + s
    return s

def _map_node_label(data_labels: List[str], repo: "Neo4jRepository") -> List[str]:
    for l in data_labels or []:
        if "owl#Class" in l or l.endswith("Class"):
            return [repo.CLASS_LABEL]
        if "NamedIndividual" in l:
            return [repo.OBJECT_LABEL]
        if "ObjectProperty" in l:
            return [repo.OBJECT_PROPERTY_LABEL]
        if "DatatypeProperty" in l or "Datatype" in l:
            return [repo.DATATYPE_PROPERTY_LABEL]
    return ["Imported"]

def sanitize_props(props: Dict[str, Any]) -> Dict[str, Any]:
    def sanitize_value(v):
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, dict):
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        if isinstance(v, list):
            out = []
            for el in v:
                if el is None or isinstance(el, (str, int, float, bool)):
                    out.append(el)
                elif isinstance(el, dict):
                    try:
                        out.append(json.dumps(el, ensure_ascii=False))
                    except Exception:
                        out.append(str(el))
                else:
                    out.append(str(el))
            return out
        return str(v)

    sanitized = {}
    for k, v in (props or {}).items():
        try:
            sanitized[k] = sanitize_value(v)
        except Exception:
            sanitized[k] = str(v)
    return sanitized

def _heuristic_label_from_uri(uri: str, repo: "Neo4jRepository"):
    if not uri:
        return ["ImportedPlaceholder"]
    # quick heuristic: resources ending with /mainResource/ -> instance (OBJECT)
    if "/mainResource/" in uri or "mainResource" in uri:
        return [repo.OBJECT_LABEL]
    # mainOntology URIs likely classes or ontology entities
    if "/mainOntology/" in uri or "mainOntology" in uri:
        # sometimes URIs point to property nodes; cannot always decide — guess CLASS
        return [repo.CLASS_LABEL]
    return ["ImportedPlaceholder"]

def import_graph_to_repo_fixed(repo: "Neo4jRepository", nodes: List[Dict[str, Any]], arcs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Улучшённый импорт:
      - индексирует входные ноды,
      - при создании рёбер подхватывает вложенные описания start_node/end_node если исходная нода отсутствует,
      - маппит rdfs:domain -> PROPERTY_DOMAIN, rdfs:range -> PROPERTY_RANGE, rdf:type -> TYPE(=REL_INSTANCE_OF),
      - создаёт плейсхолдеры только если действительно нет информации.
    Возвращает summary с mapping external_uri -> internal_uri и списками ошибок.
    """
    # индекс входных нод
    index_by_uri: Dict[str, Dict[str, Any]] = {}
    index_by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        d = n.get("data", {})
        ext = d.get("uri") or n.get("id")
        if ext:
            index_by_uri[ext] = n
        nid = n.get("id")
        if nid:
            index_by_id[nid] = n

    external_to_internal: Dict[str, str] = {}
    results = {"created_nodes": 0, "created_arcs": 0, "node_errors": [], "arc_errors": []}

    def _create_node_from_node_descriptor(descriptor: Dict[str, Any]):
        """
        descriptor — это элемент вида n (из nodes) или вложенный start_node/end_node (они имеют ключ 'data')
        """
        if not descriptor:
            raise RuntimeError("Empty node descriptor")
        # если descriptor — это контейнер с keys 'data' и 'id' (как у твоих вложенных start_node)
        if "data" in descriptor and isinstance(descriptor["data"], dict):
            d = descriptor["data"]
        else:
            d = descriptor if isinstance(descriptor, dict) else {}

        external_uri = d.get("uri") or descriptor.get("id") or d.get("id")
        labels = d.get("labels") or []
        mapped_labels = _map_node_label(labels, repo)

        props = {}
        title = _extract_label(d)
        if title:
            props["title"] = title
        desc = d.get("http://www.w3.org/2000/01/rdf-schema#comment") or d.get("rdfs:comment") or d.get("comment")
        if desc:
            props["description"] = desc
        if "params_values" in d:
            # сохраняем как JSON-строку и как разбитую карту (чтобы упростить чтение)
            try:
                props["params_values_json"] = json.dumps(d["params_values"], ensure_ascii=False)
            except Exception:
                props["params_values_json"] = str(d["params_values"])
            # также попробуем сохранить ключи-значения поверх, но только простые скаляры
            for kk, vv in (d.get("params_values") or {}).items():
                if isinstance(vv, (str, int, float, bool)):
                    props[kk] = vv
        if external_uri:
            props["external_uri"] = external_uri
        if "ontology_uri" in d:
            props["ontology_uri"] = d["ontology_uri"]
        props_safe = sanitize_props(props)
        created = repo.create_node(props_safe, labels=mapped_labels)
        return created

    def _create_placeholder_for_uri(external_uri: str):
        labels = _heuristic_label_from_uri(external_uri, repo)
        title = external_uri.rstrip("/").split("/")[-1] if external_uri else "placeholder"
        props = {"external_uri": external_uri, "title": title, "placeholder": True}
        props_safe = sanitize_props(props)
        created = repo.create_node(props_safe, labels=labels)
        return created

    # 1) Создать явно перечисленные ноды
    for n in nodes:
        try:
            d = n.get("data", {})
            external_uri = d.get("uri") or n.get("id")
            if external_uri and external_uri in external_to_internal:
                continue
            created = _create_node_from_node_descriptor(n)
            if not created:
                raise RuntimeError("create_node returned falsy")
            internal = created.get("uri")
            if external_uri:
                external_to_internal[external_uri] = internal
            results["created_nodes"] += 1
        except Exception as e:
            results["node_errors"].append({"node": n.get("id") or n.get("data", {}).get("uri"), "error": str(e)})

    # 2) Пройти по аркам — обеспечить существование концов и создать рёбра
    for a in arcs:
        try:
            source_ext = a.get("source")
            target_ext = a.get("target")

            # попытаться получить подробное описание для концов из самой арки (start_node/end_node)
            arc_data = a.get("data") or {}
            arc_start_node = arc_data.get("start_node")
            arc_end_node = arc_data.get("end_node")

            # ensure source exists
            if source_ext not in external_to_internal:
                candidate = index_by_uri.get(source_ext) or index_by_id.get(source_ext)
                if candidate:
                    created = _create_node_from_node_descriptor(candidate)
                    external_to_internal[source_ext] = created.get("uri")
                    results["created_nodes"] += 1
                elif arc_start_node and ((arc_start_node.get("data") and (arc_start_node["data"].get("uri") == source_ext))
                                         or arc_start_node.get("id") == source_ext):
                    # если в arce есть start_node с данными — используем
                    created = _create_node_from_node_descriptor(arc_start_node)
                    external_to_internal[source_ext] = created.get("uri")
                    results["created_nodes"] += 1
                else:
                    created = _create_placeholder_for_uri(source_ext)
                    external_to_internal[source_ext] = created.get("uri")
                    results["created_nodes"] += 1

            # ensure target exists
            if target_ext not in external_to_internal:
                candidate = index_by_uri.get(target_ext) or index_by_id.get(target_ext)
                if candidate:
                    created = _create_node_from_node_descriptor(candidate)
                    external_to_internal[target_ext] = created.get("uri")
                    results["created_nodes"] += 1
                elif arc_end_node and ((arc_end_node.get("data") and (arc_end_node["data"].get("uri") == target_ext))
                                       or arc_end_node.get("id") == target_ext):
                    created = _create_node_from_node_descriptor(arc_end_node)
                    external_to_internal[target_ext] = created.get("uri")
                    results["created_nodes"] += 1
                else:
                    created = _create_placeholder_for_uri(target_ext)
                    external_to_internal[target_ext] = created.get("uri")
                    results["created_nodes"] += 1

            uri1 = external_to_internal[source_ext]
            uri2 = external_to_internal[target_ext]

            rel_uri = arc_data.get("uri") or a.get("uri") or a.get("id")
            rel_props = {"predicate_uri": rel_uri}
            rel_props_safe = sanitize_props(rel_props)

            # special mapping for domain/range/type
            low = (rel_uri or "").lower()
            if "rdfs#domain" in low or low.endswith("domain") or "#domain" in low or "/domain" in low:
                # (prop)-[:PROPERTY_DOMAIN]->(class)
                repo.create_arc(uri1, uri2, rel_type=repo.REL_PROPERTY_DOMAIN, props=rel_props_safe)
            elif "rdfs#range" in low or low.endswith("range") or "#range" in low or "/range" in low:
                repo.create_arc(uri1, uri2, rel_type=repo.REL_PROPERTY_RANGE, props=rel_props_safe)
            elif "rdf-syntax-ns#type" in low or low.endswith("#type") or low.endswith("/type"):
                # ensure direction: if source is instance -> target class, create TYPE
                repo.create_arc(uri1, uri2, rel_type=repo.REL_INSTANCE_OF, props=rel_props_safe)
            else:
                # default: create sanitized rel
                rel_label = _sanitize_rel_type(rel_uri)
                repo.create_arc(uri1, uri2, rel_type=rel_label, props=rel_props_safe)

            results["created_arcs"] += 1
        except Exception as e:
            results["arc_errors"].append({"arc": a.get("id") or (a.get("data") or {}).get("uri"), "error": str(e)})

    results["mapping"] = external_to_internal
    return results


# Пример использования:
repo = Neo4jRepository(NEO4J_URI, NEO4J_USER, NEO4J_PASS)

mapping = import_graph_to_repo_fixed(repo, dictionarty['nodes'], dictionarty['arcs'])
print(mapping)
