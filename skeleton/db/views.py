from django.shortcuts import render
from django.http import StreamingHttpResponse, HttpResponseRedirect, HttpResponse
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import datetime
from django.db.models import Q
from.onthology_namespace import *
from .models import Test, Corpus, Text
from core.settings import *

# API IMPORTS
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny

# REPO IMPORTS
from db.api.TestRepository import TestRepository
from db.api.CorpusRepository import CorpusRepository
from db.api.TextRepository import TextRepository
from db.api.OntologyRepository import OntologyRepository


@api_view(['GET', ])
@permission_classes((AllowAny,))
def getTest(request):
    id = request.GET.get('id', None)
    if id is None:
        return HttpResponse(status=400)
    
    testRepo = TestRepository()
    result = testRepo.getTest(id = id)
    return Response(result)

@api_view(['POST', ])
@permission_classes((IsAuthenticated,))
def postTest(request):
    data = json.loads(request.body.decode('utf-8'))
    testRepo = TestRepository()
    test = testRepo.postTest(test_data = data)
    return JsonResponse(test)

@api_view(['DELETE', ])
@permission_classes((AllowAny,))
def deleteTest(request):
    id = request.GET.get('id', None)
    if id is None:
        return HttpResponse(status=400)
    
    testRepo = TestRepository()
    result = testRepo.deleteTest(id = id)
    return Response(result)

# ===== Corpus CRUD =====
@api_view(['POST'])
@permission_classes((AllowAny,))
def create_corpus(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = CorpusRepository()
    return JsonResponse(repo.create(data))

@api_view(['PUT', 'PATCH'])
@permission_classes((AllowAny,))
def update_corpus(request):
    corpus_id = request.GET.get('id')
    if corpus_id is None:
        return HttpResponse(status=400)
    data = json.loads(request.body.decode('utf-8'))
    repo = CorpusRepository()
    return JsonResponse(repo.update(int(corpus_id), data))

@api_view(['GET'])
@permission_classes((AllowAny,))
def get_corpus(request):
    corpus_id = request.GET.get('id')
    if corpus_id is None:
        return HttpResponse(status=400)
    repo = CorpusRepository()
    return JsonResponse(repo.get(int(corpus_id)))

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def delete_corpus(request):
    corpus_id = request.GET.get('id')
    if corpus_id is None:
        return HttpResponse(status=400)
    repo = CorpusRepository()
    return JsonResponse({'deleted': repo.delete(int(corpus_id))})

# ===== Text CRUD =====
@api_view(['POST'])
@permission_classes((AllowAny,))
def create_text(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = TextRepository()
    return JsonResponse(repo.create(data))

@api_view(['PUT', 'PATCH'])
@permission_classes((AllowAny,))
def update_text(request):
    text_id = request.GET.get('id')
    if text_id is None:
        return HttpResponse(status=400)
    data = json.loads(request.body.decode('utf-8'))
    repo = TextRepository()
    return JsonResponse(repo.update(int(text_id), data))

@api_view(['GET'])
@permission_classes((AllowAny,))
def get_text(request):
    text_id = request.GET.get('id')
    if text_id is None:
        return HttpResponse(status=400)
    repo = TextRepository()
    return JsonResponse(repo.get(int(text_id)))

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def delete_text(request):
    text_id = request.GET.get('id')
    if text_id is None:
        return HttpResponse(status=400)
    repo = TextRepository()
    return JsonResponse({'deleted': repo.delete(int(text_id))})

@api_view(['GET'])
@permission_classes((AllowAny,))
def find_similar_texts(request):
    text_id = request.GET.get('id')
    limit = int(request.GET.get('limit', 5))
    if text_id is None:
        return HttpResponse(status=400)
    repo = TextRepository()
    return JsonResponse(repo.find_similar(int(text_id), limit))

@api_view(['POST'])
@permission_classes((AllowAny,))
def search_texts_by_query(request):
    data = json.loads(request.body.decode('utf-8'))
    query_text = data.get('query')
    limit = data.get('limit', 5)
    if not query_text:
        return HttpResponse(status=400)
    repo = TextRepository()
    return JsonResponse(repo.search_by_text(query_text, limit))

# ===== Ontology endpoints (delegating to OntologyRepository) =====
@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_all_nodes(request):
    repo = OntologyRepository()
    try:
        return JsonResponse({'nodes': repo.get_all_nodes()}, safe=False)
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_create_class(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        node = repo.create_class(
            title=data.get('title', ''),
            description=data.get('description'),
            parent_title=data.get('parent_title')
        )
        return JsonResponse(node)
    finally:
        repo.close()

# === Extra ontology endpoints ===
@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_ontology(request):
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.get_ontology())
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_parent_classes(request):
    repo = OntologyRepository()
    try:
        classes = repo.get_ontology_parent_classes()
        return JsonResponse({'classes': classes}, safe=False)
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_create_arc(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        arc = repo.create_arc(
            node1_uri=data.get('node1_uri'),
            node2_uri=data.get('node2_uri'),
            rel_type=data.get('rel_type') or 'RELATED',
            props=data.get('props')
        )
        return JsonResponse(arc)
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_create_arc_by_titles(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        arc = repo.create_arc_by_titles(
            node1_title=data.get('node1_title'),
            node2_title=data.get('node2_title'),
            rel_type=data.get('rel_type') or 'RELATED',
            label1=data.get('label1'),
            label2=data.get('label2'),
            props=data.get('props')
        )
        return JsonResponse(arc)
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_all_nodes_and_arcs(request):
    repo = OntologyRepository()
    try:
        return JsonResponse({'data': repo.get_all_nodes_and_arcs()})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_node_by_uri(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.get_node_by_uri(uri) or {})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_node_by_title(request):
    label = request.GET.get('label')
    title = request.GET.get('title')
    if not title:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.get_node_by_title(label, title) or {})
    finally:
        repo.close()

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def ontology_delete_node_by_uri(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'deleted': repo.delete_node_by_uri(uri)})
    finally:
        repo.close()

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def ontology_delete_arc_by_eid(request):
    eid = request.GET.get('eid')
    if not eid:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'deleted': repo.delete_arc_by_element_id(eid)})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_run_query(request):
    data = json.loads(request.body.decode('utf-8'))
    query = data.get('query')
    if not query:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'result': repo.run_custom_query(query)})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_class(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.get_class(uri) or {})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_class_by_title(request):
    title = request.GET.get('title')
    if not title:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.get_class_by_title(title) or {})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_class_parents(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'parents': repo.get_class_parents(uri)})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_class_children(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'children': repo.get_class_children(uri)})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_class_objects(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'objects': repo.get_class_objects(uri)})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_update_class(request):
    data = json.loads(request.body.decode('utf-8'))
    uri = data.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        node = repo.update_class(uri, title=data.get('title'), description=data.get('description'))
        return JsonResponse(node or {})
    finally:
        repo.close()

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def ontology_delete_class(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'deleted': repo.delete_class(uri)})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_add_class_attribute(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.add_class_attribute(data.get('class_title'), data.get('prop_title')))
    finally:
        repo.close()

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def ontology_delete_class_attribute(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'deleted': repo.delete_class_attribute(uri)})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_add_class_object_attribute(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.add_class_object_attribute(
            class_title=data.get('class_title'),
            attr_title=data.get('attr_title'),
            range_class_title=data.get('range_class_title')
        ))
    finally:
        repo.close()

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def ontology_delete_class_object_attribute(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'deleted': repo.delete_class_object_attribute(uri)})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_add_class_parent(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        return JsonResponse({'ok': repo.add_class_parent(data.get('parent_title'), data.get('target_title'))})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_create_object(request):
    data = json.loads(request.body.decode('utf-8'))
    repo = OntologyRepository()
    try:
        node = repo.create_object(
            class_title=data.get('class_title'),
            obj_title=data.get('obj_title'),
            description=data.get('description'),
            datatype_props=data.get('datatype_props'),
            obj_params=data.get('obj_params')
        )
        return JsonResponse(node)
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_get_object(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.get_object(uri) or {})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_update_object(request):
    data = json.loads(request.body.decode('utf-8'))
    uri = data.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        node = repo.update_object(
            obj_uri=uri,
            title=data.get('title'),
            description=data.get('description'),
            datatype_props=data.get('datatype_props'),
            obj_params_to_add=data.get('obj_params_to_add'),
            obj_params_to_remove=data.get('obj_params_to_remove')
        )
        return JsonResponse(node or {})
    finally:
        repo.close()

@api_view(['DELETE'])
@permission_classes((AllowAny,))
def ontology_delete_object(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse({'deleted': repo.delete_object(uri)})
    finally:
        repo.close()

@api_view(['POST'])
@permission_classes((AllowAny,))
def ontology_update_node(request):
    data = json.loads(request.body.decode('utf-8'))
    uri = data.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        node = repo.update_node(
            uri=uri,
            props=data.get('props') or {},
            set_labels=data.get('set_labels'),
            remove_labels=data.get('remove_labels')
        )
        return JsonResponse(node or {})
    finally:
        repo.close()

@api_view(['GET'])
@permission_classes((AllowAny,))
def ontology_collect_signature(request):
    uri = request.GET.get('uri')
    if not uri:
        return HttpResponse(status=400)
    repo = OntologyRepository()
    try:
        return JsonResponse(repo.collect_signature(uri))
    finally:
        repo.close()