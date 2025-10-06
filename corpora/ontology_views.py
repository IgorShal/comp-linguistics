from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from db.api import get_ontology_repository, DriverRepository
from utils.repository_error import RepositoryError


class OntologyHealthView(APIView):
    def get(self, request):
        driver = DriverRepository()
        return Response({"ok": driver.health()})


class OntologyClassesView(APIView):
    def get(self, request):
        repo = get_ontology_repository()
        try:
            data = repo.get_ontology()
            return Response(data)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OntologyParentClassesView(APIView):
    def get(self, request):
        repo = get_ontology_repository()
        try:
            data = repo.get_ontology_parent_classes()
            return Response({"classes": data})
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassCreateView(APIView):
    def post(self, request):
        repo = get_ontology_repository()
        title = request.data.get("title")
        description = request.data.get("description")
        parent_title = request.data.get("parent_title")
        if not title:
            return Response({"error": "title is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            node = repo.create_class(title=title, description=description, parent_title=parent_title)
            return Response(node, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassDetailView(APIView):
    def get(self, request, uri: str):
        repo = get_ontology_repository()
        node = repo.get_class(uri)
        if not node:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(node)

    def patch(self, request, uri: str):
        repo = get_ontology_repository()
        try:
            node = repo.update_class(uri, title=request.data.get("title"), description=request.data.get("description"))
            if not node:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(node)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, uri: str):
        repo = get_ontology_repository()
        ok = repo.delete_class(uri)
        return Response({"deleted": ok})


class ClassByTitleView(APIView):
    def get(self, request):
        title = request.query_params.get("title")
        if not title:
            return Response({"error": "title is required"}, status=status.HTTP_400_BAD_REQUEST)
        repo = get_ontology_repository()
        node = repo.get_class_by_title(title)
        if not node:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(node)


class ClassParentsView(APIView):
    def get(self, request, uri: str):
        repo = get_ontology_repository()
        try:
            data = repo.get_class_parents(uri)
            return Response({"parents": data})
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassChildrenView(APIView):
    def get(self, request, uri: str):
        repo = get_ontology_repository()
        try:
            data = repo.get_class_children(uri)
            return Response({"children": data})
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassObjectsView(APIView):
    def get(self, request, uri: str):
        repo = get_ontology_repository()
        try:
            data = repo.get_class_objects(uri)
            return Response({"objects": data})
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassAddAttributeView(APIView):
    def post(self, request, class_title: str):
        repo = get_ontology_repository()
        try:
            prop = repo.add_class_attribute(class_title, prop_title=request.data.get("prop_title"))
            return Response(prop, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassDeleteAttributeView(APIView):
    def delete(self, request, prop_uri: str):
        repo = get_ontology_repository()
        ok = repo.delete_class_attribute(prop_uri)
        return Response({"deleted": ok})


class ClassAddObjectAttributeView(APIView):
    def post(self, request, class_title: str):
        repo = get_ontology_repository()
        try:
            prop = repo.add_class_object_attribute(
                class_title=class_title,
                attr_title=request.data.get("attr_title"),
                range_class_title=request.data.get("range_class_title")
            )
            return Response(prop, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ClassDeleteObjectAttributeView(APIView):
    def delete(self, request, object_property_uri: str):
        repo = get_ontology_repository()
        ok = repo.delete_class_object_attribute(object_property_uri)
        return Response({"deleted": ok})


class ClassAddParentView(APIView):
    def post(self, request):
        parent_title = request.data.get("parent_title")
        target_title = request.data.get("target_title")
        if not parent_title or not target_title:
            return Response({"error": "parent_title and target_title are required"}, status=status.HTTP_400_BAD_REQUEST)
        repo = get_ontology_repository()
        ok = repo.add_class_parent(parent_title=parent_title, target_title=target_title)
        return Response({"ok": ok})


class ObjectCreateView(APIView):
    def post(self, request):
        repo = get_ontology_repository()
        try:
            node = repo.create_object(
                class_title=request.data.get("class_title"),
                obj_title=request.data.get("obj_title"),
                description=request.data.get("description"),
                datatype_props=request.data.get("datatype_props"),
                obj_params=request.data.get("obj_params")
            )
            return Response(node, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ObjectDetailView(APIView):
    def get(self, request, uri: str):
        repo = get_ontology_repository()
        node = repo.get_object(uri)
        if not node:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(node)

    def patch(self, request, uri: str):
        repo = get_ontology_repository()
        try:
            node = repo.update_object(
                obj_uri=uri,
                title=request.data.get("title"),
                description=request.data.get("description"),
                datatype_props=request.data.get("datatype_props"),
                obj_params_to_add=request.data.get("obj_params_to_add"),
                obj_params_to_remove=request.data.get("obj_params_to_remove"),
            )
            if not node:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(node)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, uri: str):
        repo = get_ontology_repository()
        ok = repo.delete_object(uri)
        return Response({"deleted": ok})


class NodesListView(APIView):
    def get(self, request):
        repo = get_ontology_repository()
        return Response({"nodes": repo.get_all_nodes()})


class GraphListView(APIView):
    def get(self, request):
        repo = get_ontology_repository()
        return Response({"graph": repo.get_all_nodes_and_arcs()})


class NodesByLabelsView(APIView):
    def get(self, request):
        labels_str = request.query_params.get("labels", "")
        labels = [l for l in labels_str.split(",") if l]
        if not labels:
            return Response({"error": "labels query param required"}, status=status.HTTP_400_BAD_REQUEST)
        repo = get_ontology_repository()
        try:
            data = repo.get_nodes_by_labels(labels)
            return Response({"nodes": data})
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class NodeCreateView(APIView):
    def post(self, request):
        repo = get_ontology_repository()
        labels = request.data.get("labels") or []
        params = request.data.get("params") or {}
        try:
            node = repo.create_node(params=params, labels=labels)
            return Response(node, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class NodeDetailView(APIView):
    def get(self, request, uri: str):
        repo = get_ontology_repository()
        node = repo.get_node_by_uri(uri)
        if not node:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(node)

    def patch(self, request, uri: str):
        repo = get_ontology_repository()
        try:
            node = repo.update_node(
                uri=uri,
                props=request.data.get("props") or {},
                set_labels=request.data.get("set_labels"),
                remove_labels=request.data.get("remove_labels"),
            )
            if not node:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(node)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, uri: str):
        repo = get_ontology_repository()
        ok = repo.delete_node_by_uri(uri)
        return Response({"deleted": ok})


class NodeByTitleView(APIView):
    def get(self, request):
        title = request.query_params.get("title")
        label = request.query_params.get("label")
        if not title:
            return Response({"error": "title is required"}, status=status.HTTP_400_BAD_REQUEST)
        repo = get_ontology_repository()
        node = repo.get_node_by_title(label, title)
        if not node:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(node)


class ArcCreateView(APIView):
    def post(self, request):
        repo = get_ontology_repository()
        try:
            arc = repo.create_arc(
                node1_uri=request.data.get("node1_uri"),
                node2_uri=request.data.get("node2_uri"),
                rel_type=request.data.get("rel_type") or "RELATED",
                props=request.data.get("props") or {},
            )
            return Response(arc, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ArcByTitlesCreateView(APIView):
    def post(self, request):
        repo = get_ontology_repository()
        try:
            arc = repo.create_arc_by_titles(
                node1_title=request.data.get("node1_title"),
                node2_title=request.data.get("node2_title"),
                rel_type=request.data.get("rel_type") or "RELATED",
                label1=request.data.get("label1"),
                label2=request.data.get("label2"),
                props=request.data.get("props"),
            )
            return Response(arc, status=status.HTTP_201_CREATED)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ArcDeleteByElementIdView(APIView):
    def delete(self, request, element_id: str):
        repo = get_ontology_repository()
        ok = repo.delete_arc_by_element_id(element_id)
        return Response({"deleted": ok})


class ArcDeleteByIdView(APIView):
    def delete(self, request, arc_id: str):
        repo = get_ontology_repository()
        ok = repo.delete_arc_by_id(arc_id)
        return Response({"deleted": ok})


class ClassSignatureView(APIView):
    def get(self, request, class_uri: str):
        repo = get_ontology_repository()
        try:
            sig = repo.collect_signature(class_uri)
            return Response(sig)
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RunQueryView(APIView):
    def post(self, request):
        # ВНИМАНИЕ: только для отладки в учебных целях
        query = request.data.get("query")
        if not query:
            return Response({"error": "query is required"}, status=status.HTTP_400_BAD_REQUEST)
        repo = get_ontology_repository()
        try:
            data = repo.run_custom_query(query)
            return Response({"records": data})
        except RepositoryError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


