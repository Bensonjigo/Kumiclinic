from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import models as db_models
from django.db.models import Count
from .models import (
    Patient, Visit, Triage, Consultation, Prescription,
    Medicine, StockMovement, LabRequest, DailyReport, User
)
from .audit import log_action


# =============================================================================
# ROLE-BASED DASHBOARD VIEWS
# =============================================================================

@login_required
def dashboard_redirect(request):
    """
    Redirects logged-in users to their role-specific dashboard.
    This is the main entry point after login.
    """
    role = request.user.role
    if request.user.is_superuser:
        role = 'ADMIN'
    
    role_urls = {
        'RECEPTIONIST': 'dashboard_reception',
        'NURSE': 'dashboard_reception',
        'DOCTOR': 'dashboard_doctor',
        'LAB_TECHNICIAN': 'dashboard_lab',
        'PHARMACIST': 'dashboard_pharmacy',
        'ADMIN': 'dashboard_admin',
    }
    
    redirect_url = role_urls.get(role, 'dashboard_reception')
    return redirect(redirect_url)


@login_required
def dashboard_reception(request):
    """
    Receptionist + Nurse Combined Dashboard:
    - Patient registration form
    - New visit creation
    - Triage queue management
    - Quick stats for today
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Today's statistics
    total_patients_today = Visit.objects.filter(visit_date__gte=today_start).count()
    new_patients_today = Patient.objects.filter(created_at__gte=today_start).count()
    completed_today = Visit.objects.filter(visit_date__gte=today_start, status='COMPLETED').count()
    
    # Queue counts
    waiting_triage_count = Visit.objects.filter(status='WAITING_FOR_TRIAGE').count()
    waiting_doctor_count = Visit.objects.filter(status='WAITING_FOR_DOCTOR').count()
    
    # Waiting for triage (queryset for display)
    waiting_triage = Visit.objects.filter(
        status='WAITING_FOR_TRIAGE'
    ).select_related('patient').order_by('visit_date')
    
    # Waiting for doctor (queryset for display)
    waiting_doctor_queue = Visit.objects.filter(
        status='WAITING_FOR_DOCTOR'
    ).select_related('patient').order_by('visit_date')
    
    # Today's triage count
    triaged_today = Triage.objects.filter(
        created_at__gte=today_start
    ).count()
    
    # Recent visits today
    visits_today = Visit.objects.filter(
        visit_date__gte=today_start
    ).select_related('patient').order_by('-visit_date')[:10]
    
    context = {
        'total_patients_today': total_patients_today,
        'new_patients_today': new_patients_today,
        'completed_today': completed_today,
        'waiting_triage': waiting_triage_count,
        'waiting_doctor': waiting_doctor_count,
        'waiting_triage_list': waiting_triage,
        'waiting_doctor_queue': waiting_doctor_queue,
        'triaged_today': triaged_today,
        'waiting_triage_count': waiting_triage_count,
        'visits_today': visits_today,
    }
    return render(request, 'dashboard/reception.html', context)


@login_required
def dashboard_nurse(request):
    """
    Nurse Dashboard:
    - Patients waiting for triage
    - Quick access to triage forms
    - Today's triage count
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Patients waiting for triage
    waiting_triage = Visit.objects.filter(
        status='WAITING_FOR_TRIAGE'
    ).select_related('patient').order_by('visit_date')
    
    # Today's triage count
    triaged_today = Triage.objects.filter(
        created_at__gte=today_start
    ).count()
    
    # Queue statistics
    total_waiting = Visit.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    waiting_doctor = Visit.objects.filter(status='WAITING_FOR_DOCTOR').count()
    
    context = {
        'waiting_triage': waiting_triage,
        'triaged_today': triaged_today,
        'total_waiting': total_waiting,
        'waiting_doctor': waiting_doctor,
    }
    return render(request, 'dashboard/nurse.html', context)


@login_required
def dashboard_doctor(request):
    """
    Doctor Dashboard:
    - Patients waiting for consultation
    - Patient detail view with vitals
    - Today's consultation count
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Patients waiting for doctor (with triage data prefetched)
    waiting_consultation = Visit.objects.filter(
        status='WAITING_FOR_DOCTOR'
    ).select_related('patient', 'triage').prefetch_related('triage').order_by('visit_date')
    
    # Patients who completed lab, waiting for doctor
    in_lab = Visit.objects.filter(status='IN_LAB').select_related('patient', 'triage').order_by('visit_date')
    
    # Today's consultation count
    consultations_today = Consultation.objects.filter(
        created_at__gte=today_start
    ).count()
    
    # Recent completed visits for quick reference
    recent_completed = Visit.objects.filter(
        status='COMPLETED',
        visit_date__gte=today_start
    ).select_related('patient', 'consultation__doctor')[:10]
    
    context = {
        'waiting_consultation': waiting_consultation,
        'in_lab': in_lab,
        'consultations_today': consultations_today,
        'recent_completed': recent_completed,
    }
    return render(request, 'dashboard/doctor.html', context)


@login_required
def dashboard_lab(request):
    """
    Lab Technician Dashboard:
    - Pending lab requests
    - Completed tests today
    - Quick access to record results
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Pending lab requests
    pending_labs = LabRequest.objects.filter(
        status='PENDING'
    ).select_related('visit__patient', 'requested_by').order_by('date')
    
    # In progress labs
    in_progress_labs = LabRequest.objects.filter(
        status='IN_PROGRESS'
    ).select_related('visit__patient', 'requested_by').order_by('date')
    
    # Today's completed tests
    completed_today = LabRequest.objects.filter(
        status='COMPLETED',
        completed_date__gte=today_start
    ).count()
    
    # Total pending count
    total_pending = LabRequest.objects.filter(status='PENDING').count()
    
    context = {
        'pending_labs': pending_labs,
        'in_progress_labs': in_progress_labs,
        'completed_today': completed_today,
        'total_pending': total_pending,
    }
    return render(request, 'dashboard/lab.html', context)


@login_required
def dashboard_pharmacy(request):
    """
    Pharmacist Dashboard:
    - Pending prescriptions to dispense
    - Stock overview
    - Low stock alerts
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Pending prescriptions
    pending_prescriptions = Prescription.objects.filter(
        is_dispensed=False
    ).select_related(
        'consultation__visit__patient',
        'consultation__doctor',
        'medicine'
    ).order_by('created_at')
    
    # Today's dispensed count
    dispensed_today = Prescription.objects.filter(
        is_dispensed=True,
        updated_at__gte=today_start
    ).count()
    
    # Stock overview
    total_medicines = Medicine.objects.count()
    low_stock = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level')
    )
    low_stock_count = low_stock.count()
    low_stock_medicines = low_stock[:5]
    
    # Expired medicines
    expired_count = Medicine.objects.filter(
        expiry_date__lt=today
    ).count()
    
    context = {
        'pending_prescriptions': pending_prescriptions,
        'dispensed_today': dispensed_today,
        'total_medicines': total_medicines,
        'low_stock_count': low_stock_count,
        'low_stock_medicines': low_stock_medicines,
        'expired_count': expired_count,
    }
    return render(request, 'dashboard/pharmacy.html', context)


@login_required
def dashboard_admin(request):
    """
    Admin Dashboard:
    - Clinic summary and reports
    - Full workflow overview
    - All statistics
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # Today's statistics
    total_patients_today = Visit.objects.filter(visit_date__gte=today_start).count()
    patients_waiting = Visit.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    completed_today = Visit.objects.filter(visit_date__gte=today_start, status='COMPLETED').count()
    
    # Staff counts by role
    staff_counts = {
        'receptionists': User.objects.filter(role='RECEPTIONIST').count(),
        'nurses': User.objects.filter(role='NURSE').count(),
        'doctors': User.objects.filter(role='DOCTOR').count(),
        'lab_technicians': User.objects.filter(role='LAB_TECHNICIAN').count(),
        'pharmacists': User.objects.filter(role='PHARMACIST').count(),
    }
    
    # Workflow queue counts
    waiting_triage = Visit.objects.filter(status='WAITING_FOR_TRIAGE').count()
    waiting_doctor = Visit.objects.filter(status='WAITING_FOR_DOCTOR').count()
    in_lab = Visit.objects.filter(status='IN_LAB').count()
    waiting_pharmacy = Visit.objects.filter(status='WAITING_FOR_PHARMACY').count()
    
    # Lab and pharmacy stats
    pending_labs = LabRequest.objects.filter(status='PENDING').count()
    pending_prescriptions = Prescription.objects.filter(is_dispensed=False).count()
    
    # Stock alerts
    low_stock_count = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level')
    ).count()
    expired_count = Medicine.objects.filter(expiry_date__lt=today).count()
    
    # Recent activity
    recent_visits = Visit.objects.filter(
        visit_date__gte=today_start
    ).select_related('patient')[:10]
    
    # Low stock medicines
    low_stock_medicines = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level')
    )[:5]
    
    # Reports
    recent_reports = DailyReport.objects.all()[:7]
    
    context = {
        'total_patients_today': total_patients_today,
        'patients_waiting': patients_waiting,
        'completed_today': completed_today,
        'staff_counts': staff_counts,
        'waiting_triage': waiting_triage,
        'waiting_doctor': waiting_doctor,
        'in_lab': in_lab,
        'waiting_pharmacy': waiting_pharmacy,
        'pending_labs': pending_labs,
        'pending_prescriptions': pending_prescriptions,
        'low_stock_count': low_stock_count,
        'expired_count': expired_count,
        'recent_visits': recent_visits,
        'low_stock_medicines': low_stock_medicines,
        'recent_reports': recent_reports,
    }
    return render(request, 'dashboard/admin.html', context)


# =============================================================================
# ORIGINAL VIEWS (Kept for compatibility)
# =============================================================================

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            log_action(user, 'LOGIN', description=f'User logged in', request=request)
            return redirect('dashboard')
        messages.error(request, 'Invalid credentials')
    return render(request, 'clinic/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        log_action(request.user, 'LOGOUT', description=f'User logged out', request=request)
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    total_patients_today = Visit.objects.filter(visit_date__gte=today_start).count()
    patients_waiting = Visit.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    low_stock_count = Medicine.objects.filter(stock_quantity__lte=db_models.F('minimum_stock_level')).count()
    pending_labs = LabRequest.objects.filter(status='PENDING').count()
    completed_today = Visit.objects.filter(visit_date__gte=today_start, status='COMPLETED').count()
    
    visits_today = Visit.objects.filter(visit_date__gte=today_start).select_related('patient')[:10]
    
    low_stock_medicines = Medicine.objects.filter(stock_quantity__lte=db_models.F('minimum_stock_level'))[:5]
    
    # Workflow queue counts
    waiting_triage = Visit.objects.filter(status='WAITING_FOR_TRIAGE').count()
    waiting_doctor = Visit.objects.filter(status='WAITING_FOR_DOCTOR').count()
    waiting_pharmacy = Visit.objects.filter(status='WAITING_FOR_PHARMACY').count()
    
    context = {
        'total_patients_today': total_patients_today,
        'patients_waiting': patients_waiting,
        'low_stock_count': low_stock_count,
        'pending_labs': pending_labs,
        'completed_today': completed_today,
        'visits_today': visits_today,
        'low_stock_medicines': low_stock_medicines,
        'waiting_triage': waiting_triage,
        'waiting_doctor': waiting_doctor,
        'waiting_pharmacy': waiting_pharmacy,
    }
    return render(request, 'clinic/dashboard.html', context)


@login_required
def patients_list(request):
    patients = Patient.objects.all().order_by('-created_at')
    return render(request, 'clinic/patients.html', {'patients': patients})


@login_required
def patient_detail(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    visits = patient.visits.select_related('consultation__doctor').prefetch_related(
        'consultation__prescriptions__medicine', 'lab_requests'
    ).order_by('-visit_date')
    
    from django.core.paginator import Paginator
    paginator = Paginator(visits, 10)
    page_number = request.GET.get('page')
    visits_page = paginator.get_page(page_number)
    
    total_visits = visits.count()
    completed_visits = visits.filter(status='COMPLETED').count()
    total_prescriptions = sum(getattr(v, 'consultation', None).prescriptions.count() for v in visits if getattr(v, 'consultation', None))
    total_lab_tests = visits.filter(lab_requests__isnull=False).count()
    
    context = {
        'patient': patient,
        'visits': visits_page,
        'total_visits': total_visits,
        'completed_visits': completed_visits,
        'total_prescriptions': total_prescriptions,
        'total_lab_tests': total_lab_tests,
    }
    return render(request, 'clinic/patient_detail.html', context)


@login_required
def register_patient(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        patient_type = request.POST.get('patient_type')
        university_id = request.POST.get('university_id')
        department = request.POST.get('department')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        address = request.POST.get('address')
        gender = request.POST.get('gender')
        date_of_birth = request.POST.get('date_of_birth')
        
        # Next of Kin
        next_of_kin_name = request.POST.get('next_of_kin_name')
        next_of_kin_relationship = request.POST.get('next_of_kin_relationship')
        next_of_kin_contact = request.POST.get('next_of_kin_contact')
        next_of_kin_address = request.POST.get('next_of_kin_address')
        
        if Patient.objects.filter(university_id=university_id).exists():
            messages.error(request, 'A patient with this university ID already exists.')
            return redirect('register_patient')
        
        patient = Patient.objects.create(
            full_name=full_name,
            patient_type=patient_type,
            university_id=university_id,
            department=department,
            phone=phone,
            email=email,
            address=address,
            gender=gender,
            date_of_birth=date_of_birth,
            next_of_kin_name=next_of_kin_name,
            next_of_kin_relationship=next_of_kin_relationship,
            next_of_kin_contact=next_of_kin_contact,
            next_of_kin_address=next_of_kin_address
        )
        
        # Automatically create a visit for the patient
        visit = Visit.objects.create(
            patient=patient,
            visit_date=timezone.now(),
            reason_for_visit='New patient registration',
            status='WAITING_FOR_TRIAGE'
        )
        
        log_action(request.user, 'REGISTER', 'Patient', patient.id, 
                   f'Registered patient: {patient.full_name} ({patient.university_id})', request)
        messages.success(request, f'Patient {patient.full_name} registered and added to queue!')
        return redirect('dashboard_reception')
    
    return render(request, 'clinic/register_patient.html')


@login_required
def edit_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    if not (request.user.role in ['NURSE', 'RECEPTIONIST'] or request.user.is_superuser):
        messages.error(request, 'You do not have permission to edit patients.')
        return redirect('patient_detail', patient_id=patient.id)
    
    if request.method == 'POST':
        patient.full_name = request.POST.get('full_name')
        patient.patient_type = request.POST.get('patient_type')
        patient.university_id = request.POST.get('university_id')
        patient.department = request.POST.get('department')
        patient.phone = request.POST.get('phone')
        patient.email = request.POST.get('email')
        patient.address = request.POST.get('address')
        patient.gender = request.POST.get('gender')
        patient.date_of_birth = request.POST.get('date_of_birth')
        patient.next_of_kin_name = request.POST.get('next_of_kin_name')
        patient.next_of_kin_relationship = request.POST.get('next_of_kin_relationship')
        patient.next_of_kin_contact = request.POST.get('next_of_kin_contact')
        patient.next_of_kin_address = request.POST.get('next_of_kin_address')
        patient.save()
        
        log_action(request.user, 'UPDATE', 'Patient', patient.id, 
                   f'Updated patient: {patient.full_name} ({patient.university_id})', request)
        messages.success(request, f'Patient {patient.full_name} updated successfully!')
        return redirect('patient_detail', patient_id=patient.id)
    
    return render(request, 'clinic/edit_patient.html', {'patient': patient})


@login_required
def delete_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    if not request.user.is_superuser:
        messages.error(request, 'Only administrators can delete patients.')
        return redirect('patient_detail', patient_id=patient.id)
    
    if request.method == 'POST':
        patient_name = patient.full_name
        university_id = patient.university_id
        patient.delete()
        
        log_action(request.user, 'DELETE', 'Patient', patient_id, 
                   f'Deleted patient: {patient_name} ({university_id})', request)
        messages.success(request, f'Patient {patient_name} deleted successfully!')
        return redirect('patients')
    
    return render(request, 'clinic/delete_patient.html', {'patient': patient})


@login_required
def visits_list(request):
    visits = Visit.objects.select_related('patient').order_by('-visit_date')
    status_filter = request.GET.get('status')
    if status_filter:
        visits = visits.filter(status=status_filter)
    return render(request, 'clinic/visits.html', {'visits': visits})


@login_required
def new_visit(request):
    if request.method == 'POST':
        patient_id = request.POST.get('patient')
        reason = request.POST.get('reason_for_visit')
        
        if not patient_id:
            messages.error(request, 'Please select a patient')
            patients = Patient.objects.all()
            return render(request, 'clinic/new_visit.html', {'patients': patients})
        
        try:
            patient = get_object_or_404(Patient, id=patient_id)
        except ValueError:
            messages.error(request, 'Invalid patient selected')
            patients = Patient.objects.all()
            return render(request, 'clinic/new_visit.html', {'patients': patients})
        visit = Visit.objects.create(
            patient=patient,
            reason_for_visit=reason,
            created_by=request.user,
            status='WAITING_FOR_TRIAGE'
        )
        messages.success(request, f'Visit created for {patient.full_name}')
        return redirect('visits')
    
    patients = Patient.objects.all()
    return render(request, 'clinic/new_visit.html', {'patients': patients})


@login_required
def visit_detail(request, visit_id):
    visit = get_object_or_404(Visit.objects.select_related('patient', 'created_by'), id=visit_id)
    return render(request, 'clinic/visit_detail.html', {'visit': visit})


@login_required
def pending_triages(request):
    visits = Visit.objects.filter(status='WAITING_FOR_TRIAGE').select_related('patient')
    return render(request, 'clinic/triage_queue.html', {'visits': visits})


@login_required
def triage_form(request, visit_id):
    visit = get_object_or_404(Visit, id=visit_id)
    
    if request.method == 'POST':
        Triage.objects.create(
            visit=visit,
            temperature=request.POST.get('temperature'),
            blood_pressure=request.POST.get('blood_pressure'),
            weight=request.POST.get('weight'),
            heart_rate=request.POST.get('heart_rate'),
            symptoms=request.POST.get('symptoms'),
            nurse_notes=request.POST.get('nurse_notes'),
            recorded_by=request.user
        )
        visit.update_status('WAITING_FOR_DOCTOR')
        messages.success(request, 'Triage recorded successfully!')
        return redirect('pending_triages')
    
    return render(request, 'clinic/triage_form.html', {'visit': visit})


@login_required
def pending_consultations(request):
    visits = Visit.objects.filter(status='WAITING_FOR_DOCTOR').select_related('patient')
    return render(request, 'clinic/consultation_queue.html', {'visits': visits})


@login_required
def consultation_form(request, visit_id):
    visit = get_object_or_404(Visit.objects.select_related('patient'), id=visit_id)
    
    if hasattr(visit, 'consultation'):
        messages.error(request, 'This visit already has a consultation!')
        return redirect('pending_consultations')
    
    if request.method == 'POST':
        diagnosis = request.POST.get('diagnosis')
        if not diagnosis:
            messages.error(request, 'Diagnosis is required!')
            return redirect('consultation_form', visit_id=visit.id)
        
        consultation = Consultation.objects.create(
            visit=visit,
            doctor=request.user,
            diagnosis=diagnosis,
            doctor_notes=request.POST.get('doctor_notes', ''),
            treatment_plan=request.POST.get('treatment_plan', '')
        )
        
        medicine_id = request.POST.get('medicine')
        dosage = request.POST.get('dosage')
        quantity_str = request.POST.get('quantity')
        
        if medicine_id and quantity_str:
            try:
                quantity = int(quantity_str)
                if quantity > 0:
                    prescription = Prescription.objects.create(
                        consultation=consultation,
                        medicine_id=medicine_id,
                        dosage=dosage or '',
                        quantity=quantity
                    )
            except (ValueError, TypeError):
                pass
        
        lab_test = request.POST.get('lab_test')
        if lab_test:
            LabRequest.objects.create(
                visit=visit,
                test_name=lab_test,
                requested_by=request.user
            )
        
        next_status = 'WAITING_FOR_PHARMACY'
        if lab_test:
            next_status = 'IN_LAB'
        visit.update_status(next_status)
        
        messages.success(request, 'Consultation recorded successfully!')
        return redirect('pending_consultations')
    
    medicines = Medicine.objects.all()
    return render(request, 'clinic/consultation_form.html', {'visit': visit, 'medicines': medicines})


@login_required
def pending_labs(request):
    lab_requests = LabRequest.objects.filter(status='PENDING').select_related('visit__patient')
    return render(request, 'clinic/lab_queue.html', {'lab_requests': lab_requests})


@login_required
def lab_result_form(request, lab_id):
    lab_request = get_object_or_404(LabRequest, id=lab_id)
    
    if request.method == 'POST':
        lab_request.status = 'COMPLETED'
        lab_request.result = request.POST.get('result')
        lab_request.notes = request.POST.get('notes')
        lab_request.technician = request.user
        lab_request.completed_date = timezone.now()
        lab_request.save()
        
        messages.success(request, 'Lab result recorded!')
        return redirect('pending_labs')
    
    return render(request, 'clinic/lab_result_form.html', {'lab_request': lab_request})


@login_required
def pending_prescriptions(request):
    prescriptions = Prescription.objects.filter(
        is_dispensed=False
    ).select_related('consultation__visit__patient', 'medicine')
    return render(request, 'clinic/pharmacy_queue.html', {'prescriptions': prescriptions})


@login_required
def dispense_medicine(request, prescription_id):
    prescription = get_object_or_404(Prescription, id=prescription_id)
    
    if prescription.is_dispensed:
        messages.error(request, 'Already dispensed')
        return redirect('pending_prescriptions')
    
    medicine = prescription.medicine
    if medicine.stock_quantity < prescription.quantity:
        messages.error(request, f'Insufficient stock. Available: {medicine.stock_quantity}')
        return redirect('pending_prescriptions')
    
    prescription.is_dispensed = True
    prescription.save()
    
    log_action(request.user, 'DISPENSE', 'Prescription', prescription.id,
               f'Dispensed {prescription.quantity} {medicine.unit} of {medicine.name}', request)
    
    messages.success(request, f'Dispensed {prescription.quantity} {medicine.unit} of {medicine.name}')
    return redirect('pending_prescriptions')


@login_required
def medicines_list(request):
    medicines = Medicine.objects.all().order_by('name')
    return render(request, 'clinic/medicines.html', {'medicines': medicines})


@login_required
def add_stock(request, medicine_id):
    if request.method == 'POST':
        medicine = get_object_or_404(Medicine, id=medicine_id)
        quantity = request.POST.get('quantity')
        expiry_date = request.POST.get('expiry_date')
        
        try:
            quantity = int(quantity)
            if quantity > 0:
                StockMovement.objects.create(
                    medicine=medicine,
                    movement_type='PURCHASE',
                    quantity=quantity,
                    performed_by=request.user,
                    notes=request.POST.get('notes', '')
                )
                if expiry_date:
                    medicine.expiry_date = expiry_date
                    medicine.save()
                log_action(request.user, 'UPDATE', 'Medicine', medicine.id,
                           f'Added {quantity} {medicine.unit} to stock', request)
                messages.success(request, f'Added {quantity} {medicine.unit} to {medicine.name}')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid quantity')
    
    return redirect('medicines')


@login_required
def reports_list(request):
    reports = DailyReport.objects.all().order_by('-report_date')[:30]
    return render(request, 'clinic/reports.html', {'reports': reports})
