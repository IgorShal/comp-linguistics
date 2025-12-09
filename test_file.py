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

# простая транслитерация для кириллицы в латиницу, чтобы имена связей были читабельны
_RU_EN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"
})

def _transliterate(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return text.lower().translate(_RU_EN)

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
    Прямой импорт без догадок:
      - создаём ноды ровно из тех описаний, что уже есть в json (nodes + вложенные start_node/end_node),
      - для рёбер используем готовые source/target; если вершина не найдена — плейсхолдер,
      - тип ребра берём из uri/labels без маппинга на специальные типы,
      - возвращаем сводку с mapping external_uri -> internal_uri и ошибками.
    """
    results = {"created_nodes": 0, "created_arcs": 0, "node_errors": [], "arc_errors": []}
    unresolved_rel_labels: List[Dict[str, Any]] = []
    external_to_internal: Dict[str, str] = {}

    def _descriptor_data(desc: Dict[str, Any]) -> Dict[str, Any]:
        if not desc:
            return {}
        if "data" in desc and isinstance(desc["data"], dict):
            return desc["data"]
        return desc if isinstance(desc, dict) else {}

    def _descriptor_uri(desc: Dict[str, Any]) -> str:
        d = _descriptor_data(desc)
        return d.get("uri") or desc.get("id") or d.get("id") or ""

    def _find_descriptor_by_key(key: str) -> Dict[str, Any] | None:
        if not key:
            return None
        if key in descriptors_by_uri:
            return descriptors_by_uri[key]
        suffix = key.rstrip("/").split("/")[-1]
        if suffix in descriptors_by_uri:
            return descriptors_by_uri[suffix]
        return None

    def _create_node_from_descriptor(desc: Dict[str, Any]):
        if not desc:
            raise RuntimeError("Empty node descriptor")
        d = _descriptor_data(desc)
        external_uri = _descriptor_uri(desc)
        labels = d.get("labels") or []
        mapped_labels = _map_node_label(labels, repo)

        props = {}
        title = _extract_label(d)
        if title:
            props["title"] = title
        desc_val = d.get("http://www.w3.org/2000/01/rdf-schema#comment") or d.get("rdfs:comment") or d.get("comment")
        if desc_val:
            props["description"] = desc_val
        if "params_values" in d:
            pv = d.get("params_values") or {}
            try:
                props["params_values_json"] = json.dumps(pv, ensure_ascii=False)
            except Exception:
                props["params_values_json"] = str(pv)
            for kk, vv in pv.items():
                # сопоставление ключа с дескриптором (по полному uri, id или окончанию)
                matched = _find_descriptor_by_key(kk)
                # прокидываем оригинальный ключ
                if isinstance(vv, (str, int, float, bool)):
                    props[kk] = vv
                    # дублируем по окончанию URI для удобства чтения
                    tail = kk.rstrip("/").split("/")[-1]
                    if tail and tail not in props:
                        props[tail] = vv
                elif isinstance(vv, list):
                    props[kk] = sanitize_props({"_": vv})["_"]
                else:
                    props[kk] = sanitize_props({"_": vv})["_"]
                if matched:
                    props.setdefault("matched_params_keys", []).append(kk)
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

    # Соберём все уникальные дескрипторы нод (из nodes + вложенных в arcs)
    descriptors_by_uri: Dict[str, Dict[str, Any]] = {}
    primary_descriptors: Dict[str, Dict[str, Any]] = {}
    def _store_descriptor(ext: str, desc: Dict[str, Any], primary: bool = False):
        if not ext or not desc:
            return
        if primary and ext not in primary_descriptors:
            primary_descriptors[ext] = desc
        if ext not in descriptors_by_uri:
            descriptors_by_uri[ext] = desc
        tail = ext.rstrip("/").split("/")[-1]
        if tail and tail not in descriptors_by_uri:
            descriptors_by_uri[tail] = desc

    for n in nodes:
        ext = _descriptor_uri(n)
        _store_descriptor(ext, n, primary=True)
    for a in arcs:
        ad = a.get("data") or {}
        for key in ("start_node", "end_node"):
            desc = ad.get(key)
            ext = _descriptor_uri(desc)
            _store_descriptor(ext, desc, primary=True)

    # Создаём ноды из подготовленных дескрипторов
    for ext, desc in primary_descriptors.items():
        try:
            created = _create_node_from_descriptor(desc)
            external_to_internal[ext] = created.get("uri")
            results["created_nodes"] += 1
        except Exception as e:
            results["node_errors"].append({"node": ext, "error": str(e)})

    # Создаём рёбра
    for a in arcs:
        try:
            arc_data = a.get("data") or {}
            source_ext = a.get("source") or _descriptor_uri(arc_data.get("start_node"))
            target_ext = a.get("target") or _descriptor_uri(arc_data.get("end_node"))
            if not source_ext or not target_ext:
                raise RuntimeError("Arc missing source or target")

            if source_ext not in external_to_internal:
                created = _create_placeholder_for_uri(source_ext)
                external_to_internal[source_ext] = created.get("uri")
                results["created_nodes"] += 1
            if target_ext not in external_to_internal:
                created = _create_placeholder_for_uri(target_ext)
                external_to_internal[target_ext] = created.get("uri")
                results["created_nodes"] += 1

            uri1 = external_to_internal[source_ext]
            uri2 = external_to_internal[target_ext]

            rel_uri = a.get("uri") or arc_data.get("uri") or (arc_data.get("labels") or [None])[0] or a.get("id")
            rel_label_raw = None
            # если uri рёбра указывает на ноду-предикат — достанем её метку
            desc_rel = _find_descriptor_by_key(rel_uri)
            if desc_rel:
                rel_label_raw = _extract_label(_descriptor_data(desc_rel))
            if not rel_label_raw:
                # fallback: хвост URI или сам uri
                rel_label_raw = rel_uri.rstrip("/").split("/")[-1] if isinstance(rel_uri, str) else rel_uri
                unresolved_rel_labels.append({"arc_id": a.get("id"), "uri": rel_uri, "rel_label_used": rel_label_raw})
            rel_label_translit = _transliterate(rel_label_raw) if isinstance(rel_label_raw, str) else ""
            rel_type_from_label = _sanitize_rel_type(rel_label_translit or (rel_label_raw if isinstance(rel_label_raw, str) else ""))
            rel_type_from_uri = _sanitize_rel_type(rel_uri if isinstance(rel_uri, str) else "")
            # если метка на кириллице/пустая после санитайза — используем хвост uri/RELATED
            rel_type = rel_type_from_label if re.search(r"[A-Za-z0-9]", rel_type_from_label) else rel_type_from_uri
            if not re.search(r"[A-Za-z0-9]", rel_type):
                rel_type = "RELATED"
            rel_props = sanitize_props({
                "predicate_uri": rel_uri,
                "predicate_uri_tail": rel_uri.rstrip("/").split("/")[-1] if isinstance(rel_uri, str) else rel_uri,
                "predicate_label": rel_label_raw
            })

            repo.create_arc(uri1, uri2, rel_type=rel_type, props=rel_props)
            results["created_arcs"] += 1
        except Exception as e:
            results["arc_errors"].append({"arc": a.get("id") or (a.get("data") or {}).get("uri"), "error": str(e)})

    results["mapping"] = external_to_internal
    if unresolved_rel_labels:
        results["unresolved_rel_labels"] = unresolved_rel_labels
    return results


if __name__ == "__main__":
    # Пример использования для graph (2).json
    repo = Neo4jRepository(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    mapping = import_graph_to_repo_fixed(repo, dictionarty["nodes"], dictionarty["arcs"])
    print(mapping)
