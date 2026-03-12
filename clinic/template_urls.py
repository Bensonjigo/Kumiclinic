from django.urls import path
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from . import template_views

urlpatterns = [
    path('', RedirectView.as_view(url='/login/', permanent=False), name='home'),
    path('login/', template_views.login_view, name='login'),
    path('logout/', template_views.logout_view, name='logout'),
    
    # Profile and password change
    path('profile/', template_views.profile_view, name='profile'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='clinic/password_change.html',
        success_url='password_change_done'
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='clinic/password_change_done.html'
    ), name='password_change_done'),
    
    # Password reset URLs
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='clinic/password_reset.html',
        email_template_name='clinic/password_reset_email.html',
        subject_template_name='clinic/password_reset_subject.txt',
        success_url='password_reset_done'
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='clinic/password_reset_done.html'
    ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='clinic/password_reset_confirm.html',
        success_url='password_reset_complete'
    ), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='clinic/password_reset_complete.html'
    ), name='password_reset_complete'),
    
    # Role-based dashboards (main entry point is dashboard_redirect)
    path('dashboard/', template_views.dashboard_redirect, name='dashboard'),
    path('dashboard/role/', template_views.dashboard_redirect, name='dashboard_redirect'),
    path('dashboard/reception/', template_views.dashboard_reception, name='dashboard_reception'),
    path('dashboard/nurse/', template_views.dashboard_nurse, name='dashboard_nurse'),
    path('dashboard/doctor/', template_views.dashboard_doctor, name='dashboard_doctor'),
    path('dashboard/lab/', template_views.dashboard_lab, name='dashboard_lab'),
    path('dashboard/pharmacy/', template_views.dashboard_pharmacy, name='dashboard_pharmacy'),
    path('dashboard/admin/', template_views.dashboard_admin, name='dashboard_admin'),
    
    # Legacy dashboard (kept for backward compatibility)
    path('dashboard/all/', template_views.dashboard, name='dashboard_all'),
    
    path('patients/', template_views.patients_list, name='patients'),
    path('patient/<int:patient_id>/', template_views.patient_detail, name='patient_detail'),
    path('patient/<int:patient_id>/edit/', template_views.edit_patient, name='edit_patient'),
    path('patient/<int:patient_id>/delete/', template_views.delete_patient, name='delete_patient'),
    path('register/', template_views.register_patient, name='register_patient'),
    path('visits/', template_views.visits_list, name='visits'),
    path('visit/new/', template_views.new_visit, name='new_visit'),
    path('visit/<int:visit_id>/', template_views.visit_detail, name='visit_detail'),
    path('triage/queue/', template_views.pending_triages, name='pending_triages'),
    path('triage/<int:visit_id>/', template_views.triage_form, name='triage_form'),
    path('consultation/queue/', template_views.pending_consultations, name='pending_consultations'),
    path('consultation/<int:visit_id>/', template_views.consultation_form, name='consultation_form'),
    path('lab/queue/', template_views.pending_labs, name='pending_labs'),
    path('lab/request/new/', template_views.new_lab_request, name='new_lab_request'),
    path('lab/<int:lab_id>/', template_views.lab_result_form, name='lab_result_form'),
    path('prescription/new/', template_views.new_prescription, name='new_prescription'),
    path('pharmacy/queue/', template_views.pending_prescriptions, name='pending_prescriptions'),
    path('prescription/<int:prescription_id>/dispense/', template_views.dispense_medicine, name='dispense_medicine'),
    path('medicines/', template_views.medicines_list, name='medicines'),
    path('medicine/<int:medicine_id>/add-stock/', template_views.add_stock, name='add_stock'),
    path('reports/', template_views.reports_list, name='reports'),
]
