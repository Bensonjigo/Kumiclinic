from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'patients', views.PatientViewSet)
router.register(r'visits', views.VisitViewSet)
router.register(r'triages', views.TriageViewSet)
router.register(r'consultations', views.ConsultationViewSet)
router.register(r'prescriptions', views.PrescriptionViewSet)
router.register(r'medicines', views.MedicineViewSet)
router.register(r'stock-movements', views.StockMovementViewSet)
router.register(r'lab-requests', views.LabRequestViewSet)
router.register(r'notifications', views.NotificationViewSet)
router.register(r'reports', views.DailyReportViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('patient-data/<int:visit_id>/', views.patient_data_view, name='patient_data'),
    path('prescriptions/', views.prescription_details_api, name='prescription_details_api'),
]
