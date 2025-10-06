from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CorpusViewSet, TextViewSet
from .ontology_views import (
    OntologyHealthView,
    OntologyClassesView,
    OntologyParentClassesView,
    ClassCreateView,
    ClassDetailView,
    ClassByTitleView,
    ClassParentsView,
    ClassChildrenView,
    ClassObjectsView,
    ClassAddAttributeView,
    ClassDeleteAttributeView,
    ClassAddObjectAttributeView,
    ClassDeleteObjectAttributeView,
    ClassAddParentView,
    ObjectCreateView,
    ObjectDetailView,
    NodesListView,
    GraphListView,
    NodesByLabelsView,
    NodeCreateView,
    NodeDetailView,
    NodeByTitleView,
    ArcCreateView,
    ArcByTitlesCreateView,
    ArcDeleteByElementIdView,
    ArcDeleteByIdView,
    ClassSignatureView,
    RunQueryView,
)


router = DefaultRouter()
router.register(r'corpora', CorpusViewSet, basename='corpus')
router.register(r'texts', TextViewSet, basename='text')


urlpatterns = [
    path('', include(router.urls)),
    path('ontology/health/', OntologyHealthView.as_view(), name='ontology-health'),
    path('ontology/classes/', OntologyClassesView.as_view(), name='ontology-classes'),
    path('ontology/classes/parents/', OntologyParentClassesView.as_view(), name='ontology-parent-classes'),
    path('ontology/class/', ClassCreateView.as_view(), name='ontology-class-create'),
    path('ontology/class/by_title/', ClassByTitleView.as_view(), name='ontology-class-by-title'),
    path('ontology/class/<str:uri>/', ClassDetailView.as_view(), name='ontology-class-detail'),
    path('ontology/class/<str:uri>/parents/', ClassParentsView.as_view(), name='ontology-class-parents'),
    path('ontology/class/<str:uri>/children/', ClassChildrenView.as_view(), name='ontology-class-children'),
    path('ontology/class/<str:uri>/objects/', ClassObjectsView.as_view(), name='ontology-class-objects'),
    path('ontology/class/<str:class_title>/attributes/', ClassAddAttributeView.as_view(), name='ontology-class-add-attr'),
    path('ontology/attribute/<str:prop_uri>/', ClassDeleteAttributeView.as_view(), name='ontology-attr-delete'),
    path('ontology/class/<str:class_title>/object_attributes/', ClassAddObjectAttributeView.as_view(), name='ontology-class-add-obj-attr'),
    path('ontology/object_attribute/<str:object_property_uri>/', ClassDeleteObjectAttributeView.as_view(), name='ontology-obj-attr-delete'),
    path('ontology/class/add_parent/', ClassAddParentView.as_view(), name='ontology-class-add-parent'),
    path('ontology/objects/', ObjectCreateView.as_view(), name='ontology-object-create'),
    path('ontology/object/<str:uri>/', ObjectDetailView.as_view(), name='ontology-object-detail'),
    path('ontology/nodes/', NodesListView.as_view(), name='ontology-nodes'),
    path('ontology/graph/', GraphListView.as_view(), name='ontology-graph'),
    path('ontology/nodes/by_labels/', NodesByLabelsView.as_view(), name='ontology-nodes-by-labels'),
    path('ontology/node/', NodeCreateView.as_view(), name='ontology-node-create'),
    path('ontology/node/<str:uri>/', NodeDetailView.as_view(), name='ontology-node-detail'),
    path('ontology/node/by_title/', NodeByTitleView.as_view(), name='ontology-node-by-title'),
    path('ontology/arc/', ArcCreateView.as_view(), name='ontology-arc-create'),
    path('ontology/arc/by_titles/', ArcByTitlesCreateView.as_view(), name='ontology-arc-by-titles'),
    path('ontology/arc/element/<str:element_id>/', ArcDeleteByElementIdView.as_view(), name='ontology-arc-del-by-element'),
    path('ontology/arc/id/<str:arc_id>/', ArcDeleteByIdView.as_view(), name='ontology-arc-del-by-id'),
    path('ontology/class/<str:class_uri>/signature/', ClassSignatureView.as_view(), name='ontology-class-signature'),
    path('ontology/query/', RunQueryView.as_view(), name='ontology-run-query'),
]


