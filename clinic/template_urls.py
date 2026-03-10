from django.urls import path
from django.views.generic import RedirectView
from . import template_views

urlpatterns = [
    path('', RedirectView.as_view(url='/login/', permanent=False), name='home'),
    path('login/', template_views.login_view, name='login'),
    path('logout/', template_views.logout_view, name='logout'),
    path('dashboard/', template_views.dashboard, name='dashboard'),
    path('patients/', template_views.patients_list, name='patients'),
    path('patient/<int:patient_id>/', template_views.patient_detail, name='patient_detail'),
    path('register/', template_views.register_patient, name='register_patient'),
    path('visits/', template_views.visits_list, name='visits'),
    path('visit/new/', template_views.new_visit, name='new_visit'),
    path('visit/<int:visit_id>/', template_views.visit_detail, name='visit_detail'),
    path('triage/queue/', template_views.pending_triages, name='pending_triages'),
    path('triage/<int:visit_id>/', template_views.triage_form, name='triage_form'),
    path('consultation/queue/', template_views.pending_consultations, name='pending_consultations'),
    path('consultation/<int:visit_id>/', template_views.consultation_form, name='consultation_form'),
    path('lab/queue/', template_views.pending_labs, name='pending_labs'),
    path('lab/<int:lab_id>/', template_views.lab_result_form, name='lab_result_form'),
    path('pharmacy/queue/', template_views.pending_prescriptions, name='pending_prescriptions'),
    path('prescription/<int:prescription_id>/dispense/', template_views.dispense_medicine, name='dispense_medicine'),
    path('medicines/', template_views.medicines_list, name='medicines'),
    path('reports/', template_views.reports_list, name='reports'),
]
