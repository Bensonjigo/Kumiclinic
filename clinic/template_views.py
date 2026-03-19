from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import models as db_models
from django.db.models import Count, Sum
from django.core import serializers
import json
from .models import (
    Patient, Visit, Triage, Consultation, Prescription,
    Medicine, StockMovement, LabRequest, LabTestType, DailyReport, Report, User
)
from .audit import log_action


# =============================================================================
# AUTH VIEWS
# =============================================================================

def login_view(request):
    """Handle login form submission - works with HTML form POST"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
            return redirect('login')
    
    return render(request, 'clinic/login.html')


def logout_view(request):
    """Handle logout"""
    if request.user.is_authenticated:
        log_action(request.user, 'LOGOUT', description=f'User logged out', request=request)
    logout(request)
    return redirect('login')


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
        'NURSE': 'dashboard_nurse',
        'DOCTOR': 'dashboard_doctor',
        'LAB_TECHNICIAN': 'dashboard_lab',
        'PHARMACIST': 'dashboard_pharmacy',
        'STORE_MANAGER': 'dashboard_inventory',
        'ADMIN': 'dashboard_admin',
    }
    
    redirect_url = role_urls.get(role, 'dashboard_nurse')
    return redirect(redirect_url)


@login_required
def dashboard_nurse(request):
    """
    Nurse Dashboard (reception functions):
    - Recent patients
    - Waiting doctor queue
    - Quick stats for today
    - Patient registration
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    total_patients_today = Visit.objects.filter(visit_date__gte=today_start).count()
    new_patients_today = Patient.objects.filter(created_at__gte=today_start).count()
    completed_today = Visit.objects.filter(visit_date__gte=today_start, status='COMPLETED').count()
    
    waiting_doctor_count = Visit.objects.filter(status='WAITING_FOR_DOCTOR').count()
    
    recent_patients = list(Patient.objects.filter(
        created_at__gte=today_start
    ).order_by('-created_at'))
    
    recent_visits = list(Visit.objects.filter(
        visit_date__gte=today_start
    ).exclude(
        patient__in=recent_patients
    ).select_related('patient').order_by('-visit_date')[:10])
    
    waiting_doctor_queue = Visit.objects.filter(
        status='WAITING_FOR_DOCTOR'
    ).select_related('patient').order_by('visit_date')
    
    visits_today = Visit.objects.filter(
        visit_date__gte=today_start
    ).select_related('patient').order_by('-visit_date')[:10]
    
    context = {
        'total_patients_today': total_patients_today,
        'new_patients_today': new_patients_today,
        'completed_today': completed_today,
        'waiting_doctor': waiting_doctor_count,
        'recent_patients': recent_patients,
        'recent_visits': recent_visits,
        'recent_total': len(recent_patients) + len(recent_visits),
        'waiting_doctor_queue': waiting_doctor_queue,
        'visits_today': visits_today,
    }
    return render(request, 'dashboard/reception.html', context)


@login_required
def dashboard_doctor(request):
    """
    Doctor Dashboard:
    - Patients waiting for consultation (no lab)
    - Patients waiting for lab results
    - Patients with lab results ready (need prescription)
    - Today's consultation count
    """
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    
    # 1. Patients waiting for consultation (WAITING_FOR_DOCTOR status)
    waiting_for_consultation = Visit.objects.filter(
        status='WAITING_FOR_DOCTOR',
        lab_requests__isnull=True
    ).exclude(
        consultation__diagnosis__isnull=False
    ).distinct().select_related('patient', 'triage').order_by('visit_date')
    
    # 2. Patients currently in lab (IN_LAB status, not all tests complete)
    in_lab = []
    lab_visits = Visit.objects.filter(
        status='IN_LAB'
    ).select_related('patient', 'triage').prefetch_related('lab_requests').order_by('visit_date')
    
    for visit in lab_visits:
        lab_requests = list(visit.lab_requests.all())
        total_labs = len(lab_requests)
        completed_labs = sum(1 for lr in lab_requests if lr.status == 'COMPLETED')
        visit.lab_total = total_labs
        visit.lab_completed = completed_labs
        # Only show if not all tests are complete
        if completed_labs < total_labs:
            in_lab.append(visit)
    
    # 3. Lab results ready (IN_LAB or WAITING_FOR_DOCTOR but all tests complete) - need prescription
    lab_results_ready = []
    # Also include WAITING_FOR_DOCTOR visits that have completed labs but no consultation
    lab_visits_ready = Visit.objects.filter(
        status__in=['IN_LAB', 'WAITING_FOR_DOCTOR']
    ).select_related('patient', 'triage').prefetch_related('lab_requests', 'consultation').order_by('visit_date')
    
    for visit in lab_visits_ready:
        lab_requests = list(visit.lab_requests.all())
        if not lab_requests:
            continue
        total_labs = len(lab_requests)
        completed_labs = sum(1 for lr in lab_requests if lr.status == 'COMPLETED')
        visit.lab_total = total_labs
        visit.lab_completed = completed_labs
        # Only show if all tests are complete AND no consultation yet
        if total_labs > 0 and completed_labs == total_labs and not getattr(visit, 'consultation', None):
            lab_results_ready.append(visit)
    
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
        'waiting_for_consultation': waiting_for_consultation,
        'in_lab': in_lab,
        'lab_results_ready': lab_results_ready,
        'consultations_today': consultations_today,
        'recent_completed': recent_completed,
    }
    return render(request, 'dashboard/doctor.html', context)


@login_required
def consultation_history(request):
    """View all consultations and patient history"""
    # Get all visits with consultations (regardless of status)
    completed_visits = Visit.objects.filter(
        consultation__isnull=False
    ).select_related(
        'patient', 'consultation__doctor'
    ).prefetch_related(
        'consultation__prescriptions__medicine',
        'lab_requests'
    ).order_by('-visit_date')[:50]
    
    return render(request, 'clinic/consultation_history.html', {
        'completed_visits': completed_visits
    })


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
def lab_history(request):
    """Lab Technician History - all completed lab tests"""
    lab_requests = LabRequest.objects.filter(
        status='COMPLETED'
    ).select_related(
        'visit__patient', 'requested_by'
    ).order_by('-completed_date')[:50]
    
    return render(request, 'clinic/lab_history.html', {
        'lab_requests': lab_requests
    })


@login_required
def pharmacy_history(request):
    """Pharmacist History - all dispensed prescriptions"""
    prescriptions = Prescription.objects.filter(
        is_dispensed=True
    ).select_related(
        'consultation__visit__patient', 'consultation__doctor', 'medicine'
    ).order_by('-created_at')[:50]
    
    return render(request, 'clinic/pharmacy_history.html', {
        'prescriptions': prescriptions
    })


@login_required
def nurse_history(request):
    """Nurse History - all triages done"""
    triages = Triage.objects.select_related(
        'visit__patient', 'recorded_by'
    ).order_by('-created_at')[:50]
    
    return render(request, 'clinic/nurse_history.html', {
        'triages': triages
    })


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
    
    # Pending prescriptions - group by visit
    prescriptions = Prescription.objects.filter(
        is_dispensed=False
    ).select_related(
        'consultation__visit__patient',
        'consultation__doctor',
        'medicine'
    ).order_by('created_at')
    
    # Group by visit
    grouped_prescriptions = {}
    for rx in prescriptions:
        visit = rx.consultation.visit
        if visit.id not in grouped_prescriptions:
            grouped_prescriptions[visit.id] = {
                'visit': visit,
                'patient': visit.patient,
                'doctor': rx.consultation.doctor,
                'prescriptions': [rx],
            }
        else:
            grouped_prescriptions[visit.id]['prescriptions'].append(rx)
    
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
    
    context = {
        'grouped_prescriptions': grouped_prescriptions.values(),
        'dispensed_today': dispensed_today,
        'total_medicines': total_medicines,
        'low_stock_count': low_stock_count,
        'low_stock_medicines': low_stock_medicines,
    }
    return render(request, 'dashboard/pharmacy.html', context)


@login_required
def dashboard_admin(request):
    """
    Admin Dashboard - Focus on Inventory:
    - Medicine inventory overview
    - Stock alerts
    - Quick actions for managing inventory
    """
    # Medicine statistics
    total_medicines = Medicine.objects.count()
    low_stock_count = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level')
    ).count()
    out_of_stock = Medicine.objects.filter(stock_quantity=0).count()
    in_stock = total_medicines - low_stock_count - out_of_stock
    
    # Low stock medicines
    low_stock_medicines = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level')
    ).order_by('stock_quantity')[:10]
    
    # Out of stock medicines
    out_of_stock_medicines = Medicine.objects.filter(
        stock_quantity=0
    ).order_by('name')[:5]
    
    # Recent stock movements
    recent_movements = StockMovement.objects.select_related(
        'medicine', 'performed_by'
    ).order_by('-created_at')[:10]
    
    # Pharmacy stats
    pending_prescriptions = Prescription.objects.filter(is_dispensed=False).count()
    dispensed_today = Prescription.objects.filter(
        is_dispensed=True,
        updated_at__gte=timezone.now().date()
    ).count()
    
    context = {
        'total_medicines': total_medicines,
        'low_stock_count': low_stock_count,
        'out_of_stock': out_of_stock,
        'in_stock': in_stock,
        'low_stock_medicines': low_stock_medicines,
        'out_of_stock_medicines': out_of_stock_medicines,
        'recent_movements': recent_movements,
        'pending_prescriptions': pending_prescriptions,
        'dispensed_today': dispensed_today,
    }
    return render(request, 'dashboard/admin.html', context)


@login_required
def dashboard_inventory(request):
    """
    Inventory Dashboard (Store Manager):
    - Medicine inventory overview
    - Stock alerts
    - Quick actions for managing inventory
    """
    from django.db.models import Sum
    
    # Medicine statistics
    total_medicines = Medicine.objects.count()
    low_stock_count = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level'),
        stock_quantity__gt=0
    ).count()
    out_of_stock = Medicine.objects.filter(stock_quantity=0).count()
    in_stock = total_medicines - low_stock_count - out_of_stock
    
    # Category breakdown
    category_stats = Medicine.objects.values('category').annotate(
        count=Count('id'),
        total_stock=Sum('stock_quantity')
    ).order_by('-count')
    
    # Supplier breakdown
    supplier_stats = Medicine.objects.exclude(supplier='').values('supplier').annotate(
        count=Count('id'),
        total_stock=Sum('stock_quantity')
    ).order_by('-count')[:5]
    
    # Low stock medicines
    low_stock_medicines = Medicine.objects.filter(
        stock_quantity__lte=db_models.F('minimum_stock_level'),
        stock_quantity__gt=0
    ).order_by('stock_quantity')[:10]
    
    # Out of stock medicines
    out_of_stock_medicines = Medicine.objects.filter(
        stock_quantity=0
    ).order_by('name')[:5]
    
    # Recent stock movements
    recent_movements = StockMovement.objects.select_related(
        'medicine', 'performed_by'
    ).order_by('-created_at')[:10]
    
    # Stock movement today
    movements_today = StockMovement.objects.filter(
        created_at__date=timezone.now().date()
    ).aggregate(
        total_in=Sum('quantity', filter=db_models.Q(movement_type='PURCHASE')),
        total_out=Sum('quantity', filter=db_models.Q(movement_type='DISPENSE'))
    )
    
    # Pharmacy stats
    pending_prescriptions = Prescription.objects.filter(is_dispensed=False).count()
    dispensed_today = Prescription.objects.filter(
        is_dispensed=True,
        updated_at__gte=timezone.now().date()
    ).count()
    
    context = {
        'total_medicines': total_medicines,
        'low_stock_count': low_stock_count,
        'out_of_stock': out_of_stock,
        'in_stock': in_stock,
        'category_stats': category_stats,
        'supplier_stats': supplier_stats,
        'low_stock_medicines': low_stock_medicines,
        'out_of_stock_medicines': out_of_stock_medicines,
        'recent_movements': recent_movements,
        'movements_today': movements_today,
        'pending_prescriptions': pending_prescriptions,
        'dispensed_today': dispensed_today,
    }
    return render(request, 'dashboard/inventory.html', context)


@login_required
def profile_view(request):
    user = request.user
    
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
        
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    return render(request, 'clinic/profile.html', {'user': user})


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
        year_of_birth = request.POST.get('year_of_birth')
        
        # Calculate date of birth from year of birth
        if year_of_birth:
            try:
                year = int(year_of_birth)
                date_of_birth = timezone.now().date().replace(month=1, day=1, year=year)
            except (ValueError, TypeError):
                date_of_birth = None
        else:
            date_of_birth = None
        
        # Next of Kin
        next_of_kin_name = request.POST.get('next_of_kin_name')
        next_of_kin_relationship = request.POST.get('next_of_kin_relationship')
        next_of_kin_contact = request.POST.get('next_of_kin_contact')
        next_of_kin_address = request.POST.get('next_of_kin_address')
        
        # Visit Details
        reason_for_visit = request.POST.get('reason_for_visit')
        
        # Check for duplicate university_id only if provided
        if university_id:
            if Patient.objects.filter(university_id=university_id).exists():
                messages.error(request, 'A patient with this university ID already exists.')
                return redirect('register_patient')
        else:
            # Generate unique ID for patients without university_id
            import uuid
            university_id = f"EXT-{uuid.uuid4().hex[:8].upper()}"
        
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
        
        # Create visit with reason
        visit = Visit.objects.create(
            patient=patient,
            visit_date=timezone.now(),
            reason_for_visit=reason_for_visit or 'New patient registration',
            status='WAITING_FOR_DOCTOR',
            created_by=request.user
        )
        
        # Record vital signs only if any data is provided
        temperature = request.POST.get('temperature')
        blood_pressure = request.POST.get('blood_pressure')
        weight = request.POST.get('weight')
        
        # Check if any vital sign field has actual data (not empty string)
        has_vitals = (temperature and temperature.strip() and temperature != '') or \
                     (blood_pressure and blood_pressure.strip() and blood_pressure != '') or \
                     (weight and weight.strip() and weight != '')
        
        if has_vitals:
            Triage.objects.create(
                visit=visit,
                temperature=temperature or None,
                blood_pressure=blood_pressure or None,
                weight=weight or None,
                heart_rate=request.POST.get('heart_rate') or None,
                symptoms=request.POST.get('symptoms') or '',
                nurse_notes=request.POST.get('nurse_notes') or '',
                recorded_by=request.user
            )
        
        log_action(request.user, 'REGISTER', 'Patient', patient.id, 
                   f'Registered patient: {patient.full_name} ({patient.university_id})', request)
        if has_vitals:
            messages.success(request, f'Patient {patient.full_name} registered with visit and vital signs!')
        else:
            messages.success(request, f'Patient {patient.full_name} registered successfully!')
        return redirect('dashboard')
    
    return render(request, 'clinic/register_patient.html')


@login_required
def edit_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    if not (request.user.role == 'NURSE' or request.user.is_superuser):
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
            patients_list = list(patients.values('id', 'full_name', 'university_id', 'patient_type', 'phone'))
            return render(request, 'clinic/new_visit.html', {'patients': patients, 'patients_json': json.dumps(patients_list)})
        
        try:
            patient = get_object_or_404(Patient, id=patient_id)
        except ValueError:
            messages.error(request, 'Invalid patient selected')
            patients = Patient.objects.all()
            patients_list = list(patients.values('id', 'full_name', 'university_id', 'patient_type', 'phone'))
            return render(request, 'clinic/new_visit.html', {'patients': patients, 'patients_json': json.dumps(patients_list)})
        
        visit = Visit.objects.create(
            patient=patient,
            reason_for_visit=reason or 'New visit',
            created_by=request.user,
            status='WAITING_FOR_DOCTOR'
        )
        
        # Record vital signs only if any data is provided
        temperature = request.POST.get('temperature')
        blood_pressure = request.POST.get('blood_pressure')
        weight = request.POST.get('weight')
        
        # Check if any vital sign field has actual data (not empty string)
        has_vitals = (temperature and temperature.strip() and temperature != '') or \
                     (blood_pressure and blood_pressure.strip() and blood_pressure != '') or \
                     (weight and weight.strip() and weight != '')
        
        if has_vitals:
            Triage.objects.create(
                visit=visit,
                temperature=temperature or None,
                blood_pressure=blood_pressure or None,
                weight=weight or None,
                heart_rate=request.POST.get('heart_rate') or None,
                symptoms=request.POST.get('symptoms') or '',
                nurse_notes=request.POST.get('nurse_notes') or '',
                recorded_by=request.user
            )
        
        if has_vitals:
            messages.success(request, f'Visit created and vital signs recorded for {patient.full_name}')
        else:
            messages.success(request, f'Visit created for {patient.full_name}')
        return redirect('dashboard')
    
    patients = Patient.objects.all()
    patients_list = list(patients.values('id', 'full_name', 'university_id', 'patient_type', 'phone'))
    return render(request, 'clinic/new_visit.html', {
        'patients': patients,
        'patients_json': json.dumps(patients_list)
    })


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
    # Get visits waiting for doctor that don't have consultations yet
    visits = Visit.objects.filter(
        status='WAITING_FOR_DOCTOR'
    ).exclude(
        consultation__isnull=False
    ).select_related('patient', 'triage').prefetch_related('lab_requests').order_by('visit_date')
    return render(request, 'clinic/consultation_queue.html', {'visits': visits})


@login_required
def consultation_form(request, visit_id):
    visit = get_object_or_404(Visit.objects.select_related('patient'), id=visit_id)
    
    # If already has a consultation with a valid diagnosis (not 'Pending' or empty), don't allow editing
    if hasattr(visit, 'consultation') and visit.consultation.diagnosis and visit.consultation.diagnosis.strip() and visit.consultation.diagnosis.lower() != 'pending':
        messages.error(request, 'This visit already has a consultation!')
        return redirect('pending_consultations')
    
    if request.method == 'POST':
        # Check if this is just ordering lab tests (separate button)
        if request.POST.get('order_lab_tests'):
            lab_tests = request.POST.getlist('lab_test')
            if not lab_tests:
                messages.error(request, 'Please select at least one lab test!')
                return redirect('consultation_form', visit_id=visit.id)
            
            lab_count = 0
            for lab_test in lab_tests:
                if lab_test:
                    LabRequest.objects.create(
                        visit=visit,
                        test_name=lab_test,
                        requested_by=request.user
                    )
                    lab_count += 1
            
            visit.update_status('IN_LAB')
            messages.success(request, f'{lab_count} lab test(s) ordered. Patient moved to lab queue.')
            return redirect('pending_consultations')
        
        # Full consultation save
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
        
        # Handle multiple lab tests FIRST
        lab_tests = request.POST.getlist('lab_test')
        lab_count = 0
        for lab_test in lab_tests:
            if lab_test:
                LabRequest.objects.create(
                    visit=visit,
                    test_name=lab_test,
                    requested_by=request.user
                )
                lab_count += 1
        
        # If lab tests ordered, doctor MUST wait for results before prescribing
        # No prescriptions allowed in initial consultation if labs are ordered
        if lab_count > 0:
            visit.update_status('IN_LAB')
            msg = f'Consultation saved. {lab_count} lab test(s) ordered. You must wait for lab results before prescribing.'
            messages.success(request, msg)
            return redirect('pending_consultations')
        
        # If NO lab tests, then allow prescriptions
        medicine_ids = request.POST.getlist('medicine')
        dosages = request.POST.getlist('dosage')
        quantities = request.POST.getlist('quantity')
        
        prescription_count = 0
        for i in range(len(medicine_ids)):
            medicine_id = medicine_ids[i]
            quantity_str = quantities[i] if i < len(quantities) else None
            
            if medicine_id and quantity_str:
                try:
                    quantity = int(quantity_str)
                    if quantity > 0:
                        Prescription.objects.create(
                            consultation=consultation,
                            medicine_id=medicine_id,
                            dosage=dosages[i] if i < len(dosages) else '',
                            quantity=quantity
                        )
                        prescription_count += 1
                except (ValueError, TypeError):
                    pass
        
        # Determine next status based on prescriptions
        if prescription_count > 0:
            next_status = 'WAITING_FOR_PHARMACY'
        else:
            next_status = 'COMPLETED'
        visit.update_status(next_status)
        
        msg = 'Consultation recorded successfully!'
        if prescription_count > 0:
            msg += f' {prescription_count} prescription(s) added.'
        messages.success(request, msg)
        return redirect('pending_consultations')
    
    medicines = Medicine.objects.all()
    return render(request, 'clinic/consultation_form.html', {'visit': visit, 'medicines': medicines})


@login_required
def pending_labs(request):
    lab_requests = LabRequest.objects.filter(status='PENDING').select_related('visit__patient')
    return render(request, 'clinic/lab_queue.html', {'lab_requests': lab_requests})


@login_required
def new_lab_request(request):
    visit_id = request.GET.get('visit_id')
    visit = None
    if visit_id:
        visit = get_object_or_404(Visit, id=visit_id)
    
    # Get lab test types from database
    lab_test_types = LabTestType.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        visit_id = request.POST.get('visit_id')
        test_type_id = request.POST.get('test_type')
        custom_test_name = request.POST.get('custom_test_name', '')
        notes = request.POST.get('notes', '')
        
        visit = get_object_or_404(Visit, id=visit_id)
        
        # Create lab request with the selected test type
        lab_request = LabRequest.objects.create(
            visit=visit,
            notes=notes,
            requested_by=request.user
        )
        
        if test_type_id:
            lab_request.test_type_id = test_type_id
        elif custom_test_name:
            lab_request.custom_test_name = custom_test_name
            lab_request.test_name = 'OTHER'
        
        lab_request.save()
        
        # Update visit status to IN_LAB if not already
        if visit.status == 'WAITING_FOR_DOCTOR':
            visit.update_status('IN_LAB')
        
        messages.success(request, 'Lab test ordered successfully!')
        return redirect('dashboard_doctor')
    
    return render(request, 'clinic/new_lab_request.html', {
        'visit': visit,
        'lab_test_types': lab_test_types
    })


@login_required
def manage_lab_tests(request):
    """Manage lab test types - for admin only"""
    if not request.user.is_superuser and request.user.role != 'ADMIN':
        messages.error(request, 'You do not have permission to manage lab tests.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        # Add new test type
        if 'add_test' in request.POST:
            name = request.POST.get('name')
            code = request.POST.get('code')
            description = request.POST.get('description', '')
            
            if name and code:
                LabTestType.objects.create(
                    name=name,
                    code=code.upper(),
                    description=description
                )
                messages.success(request, f'Lab test "{name}" added successfully!')
            else:
                messages.error(request, 'Name and Code are required.')
        
        # Toggle active status
        elif 'toggle_test' in request.POST:
            test_id = request.POST.get('test_id')
            test = get_object_or_404(LabTestType, id=test_id)
            test.is_active = not test.is_active
            test.save()
            messages.success(request, f'Lab test "{test.name}" {"activated" if test.is_active else "deactivated"}!')
        
        # Delete test
        elif 'delete_test' in request.POST:
            test_id = request.POST.get('test_id')
            test = get_object_or_404(LabTestType, id=test_id)
            test_name = test.name
            test.delete()
            messages.success(request, f'Lab test "{test_name}" deleted!')
        
        return redirect('manage_lab_tests')
    
    lab_tests = LabTestType.objects.all().order_by('name')
    return render(request, 'clinic/manage_lab_tests.html', {'lab_tests': lab_tests})


@login_required
def new_prescription(request):
    visit_id = request.GET.get('visit_id')
    visit = None
    if visit_id:
        visit = get_object_or_404(Visit, id=visit_id)
    
    if request.method == 'POST':
        visit_id = request.POST.get('visit_id')
        notes = request.POST.get('notes', '')
        diagnosis = request.POST.get('diagnosis', '')
        treatment_plan = request.POST.get('treatment_plan', '')
        
        visit = get_object_or_404(Visit, id=visit_id)
        
        # Get or create consultation
        consultation = getattr(visit, 'consultation', None)
        if not consultation:
            # Create consultation if it doesn't exist (e.g., patient came from lab)
            consultation = Consultation.objects.create(
                visit=visit,
                doctor=request.user,
                diagnosis=diagnosis,
                treatment_plan=treatment_plan,
                doctor_notes=notes
            )
        
        medicine_ids = request.POST.getlist('medicine[]')
        dosages = request.POST.getlist('dosage[]')
        quantities = request.POST.getlist('quantity[]')
        
        prescription_count = 0
        for i in range(len(medicine_ids)):
            if medicine_ids[i]:
                try:
                    medicine = get_object_or_404(Medicine, id=medicine_ids[i])
                    
                    # Build dosage string from the three new fields
                    dosage_per_day = request.POST.getlist('dosage_per_day[]')
                    times_per_day = request.POST.getlist('times_per_day[]')
                    num_days = request.POST.getlist('num_days[]')
                    
                    dosage_str = ''
                    if i < len(dosages) and dosages[i]:
                        dosage_str = dosages[i]
                    elif i < len(dosage_per_day) and dosage_per_day[i] and i < len(times_per_day) and times_per_day[i] and i < len(num_days) and num_days[i]:
                        dosage_str = f"{dosage_per_day[i]} tablet(s) {times_per_day[i]} time(s) daily for {num_days[i]} days"
                    
                    Prescription.objects.create(
                        consultation=consultation,
                        medicine=medicine,
                        dosage=dosage_str,
                        quantity=int(quantities[i]) if i < len(quantities) and quantities[i] else 1,
                        notes=notes
                    )
                    prescription_count += 1
                except (ValueError, TypeError):
                    pass
        
        if prescription_count > 0:
            # Update visit status to waiting for pharmacy (handles both WAITING_FOR_DOCTOR and IN_LAB)
            if visit.status in ['WAITING_FOR_DOCTOR', 'IN_LAB']:
                visit.update_status('WAITING_FOR_PHARMACY')
        
        messages.success(request, f'{prescription_count} prescription(s) created successfully!')
        return redirect('dashboard_doctor')
    
    medicines = Medicine.objects.all()
    return render(request, 'clinic/new_prescription.html', {'visit': visit, 'medicines': medicines})


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
        
        # Check if all lab tests for this visit are now complete
        visit = lab_request.visit
        pending_labs = visit.lab_requests.filter(status__in=['PENDING', 'IN_PROGRESS']).count()
        
        if pending_labs == 0:
            # All labs complete - return to doctor for prescription
            visit.update_status('WAITING_FOR_DOCTOR')
        
        messages.success(request, 'Lab result recorded!')
        return redirect('pending_labs')
    
    return render(request, 'clinic/lab_result_form.html', {'lab_request': lab_request})


@login_required
def pending_prescriptions(request):
    prescriptions = Prescription.objects.filter(
        is_dispensed=False
    ).select_related('consultation__visit__patient', 'consultation__doctor', 'medicine').order_by('consultation__visit__visit_date')
    
    # Group by visit
    grouped = {}
    for rx in prescriptions:
        visit = rx.consultation.visit
        if visit.id not in grouped:
            grouped[visit.id] = {
                'visit': visit,
                'patient': visit.patient,
                'doctor': rx.consultation.doctor,
                'prescriptions': [rx],
            }
        else:
            grouped[visit.id]['prescriptions'].append(rx)
    
    return render(request, 'clinic/pharmacy_queue.html', {'grouped_prescriptions': grouped.values()})


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
    
    # Check if all prescriptions for this visit are now dispensed
    visit = prescription.consultation.visit
    all_prescriptions = Prescription.objects.filter(consultation__visit=visit)
    pending_count = all_prescriptions.filter(is_dispensed=False).count()
    
    if pending_count == 0:
        # All prescriptions dispensed - mark visit as completed
        visit.update_status('COMPLETED')
    
    log_action(request.user, 'DISPENSE', 'Prescription', prescription.id,
               f'Dispensed {prescription.quantity} {medicine.unit} of {medicine.name}', request)
    
    messages.success(request, f'Dispensed {prescription.quantity} {medicine.unit} of {medicine.name}')
    return redirect('pending_prescriptions')


@login_required
def dispense_all_prescriptions(request, visit_id):
    visit = get_object_or_404(Visit, id=visit_id)
    prescriptions = Prescription.objects.filter(
        consultation__visit=visit,
        is_dispensed=False
    )
    
    if not prescriptions.exists():
        messages.error(request, 'No prescriptions to dispense')
        return redirect('pending_prescriptions')
    
    # Check stock for all
    for rx in prescriptions:
        if rx.medicine.stock_quantity < rx.quantity:
            messages.error(request, f'Insufficient stock for {rx.medicine.name}')
            return redirect('pending_prescriptions')
    
    # Dispense all
    dispensed_count = 0
    for rx in prescriptions:
        rx.is_dispensed = True
        rx.save()
        
        # Deduct stock
        rx.medicine.stock_quantity -= rx.quantity
        rx.medicine.save()
        
        # Record movement
        StockMovement.objects.create(
            medicine=rx.medicine,
            movement_type='DISPENSE',
            quantity=rx.quantity,
            performed_by=request.user,
            notes=f'Dispensed for Visit #{visit.id}'
        )
        
        log_action(request.user, 'DISPENSE', 'Prescription', rx.id,
                  f'Dispensed {rx.quantity} {rx.medicine.unit} of {rx.medicine.name}', request)
        dispensed_count += 1
    
    # Update visit status
    if visit.status == 'WAITING_FOR_PHARMACY':
        visit.update_status('COMPLETED')
    
    messages.success(request, f'Dispensed {dispensed_count} prescription(s) successfully')
    return redirect('pending_prescriptions')


@login_required
def medicines_list(request):
    medicines = Medicine.objects.all().order_by('name')
    
    # Calculate summary counts
    in_stock_count = sum(1 for m in medicines if m.stock_quantity > 0 and not m.is_low_stock)
    low_stock_count = sum(1 for m in medicines if m.is_low_stock and m.stock_quantity > 0)
    out_of_stock_count = sum(1 for m in medicines if m.stock_quantity == 0)
    
    return render(request, 'clinic/medicines.html', {
        'medicines': medicines,
        'in_stock_count': in_stock_count,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count
    })


@login_required
def add_medicine(request):
    """Create a new medicine"""
    if request.user.role not in ['ADMIN', 'STORE_MANAGER'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to add medicines.')
        return redirect('medicines')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        category = request.POST.get('category')
        stock_quantity = request.POST.get('stock_quantity', 0)
        unit = request.POST.get('unit')
        minimum_stock_level = request.POST.get('minimum_stock_level', 10)
        supplier = request.POST.get('supplier', '')
        supplier_contact = request.POST.get('supplier_contact', '')
        location = request.POST.get('location', '')
        
        if name and category and unit:
            if Medicine.objects.filter(name__iexact=name).exists():
                messages.error(request, f'A medicine with the name "{name}" already exists. Please use a different name.')
                return redirect('add_medicine')
            
            medicine = Medicine.objects.create(
                name=name,
                category=category,
                stock_quantity=int(stock_quantity) if stock_quantity else 0,
                unit=unit,
                minimum_stock_level=int(minimum_stock_level) if minimum_stock_level else 10,
                supplier=supplier,
                supplier_contact=supplier_contact,
                location=location
            )
            
            # Record initial stock if quantity > 0
            if medicine.stock_quantity > 0:
                StockMovement.objects.create(
                    medicine=medicine,
                    movement_type='PURCHASE',
                    quantity=medicine.stock_quantity,
                    performed_by=request.user,
                    notes='Initial stock'
                )
            
            log_action(request.user, 'CREATE', 'Medicine', medicine.id,
                       f'Created medicine: {medicine.name}', request)
            messages.success(request, f'Medicine "{name}" created successfully!')
            return redirect('medicines')
        else:
            messages.error(request, 'Name, category, and unit are required.')
    
    return render(request, 'clinic/add_medicine.html')


@login_required
def edit_medicine(request, medicine_id):
    """Edit an existing medicine"""
    if request.user.role not in ['ADMIN', 'STORE_MANAGER'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to edit medicines.')
        return redirect('medicines')
    
    medicine = get_object_or_404(Medicine, id=medicine_id)
    
    if request.method == 'POST':
        medicine.name = request.POST.get('name')
        medicine.category = request.POST.get('category')
        medicine.unit = request.POST.get('unit')
        medicine.minimum_stock_level = int(request.POST.get('minimum_stock_level', 10)) or 10
        medicine.supplier = request.POST.get('supplier', '')
        medicine.supplier_contact = request.POST.get('supplier_contact', '')
        medicine.location = request.POST.get('location', '')
        medicine.save()
        
        log_action(request.user, 'UPDATE', 'Medicine', medicine.id,
                   f'Updated medicine: {medicine.name}', request)
        messages.success(request, f'Medicine "{medicine.name}" updated successfully!')
        return redirect('medicines')
    
    return render(request, 'clinic/edit_medicine.html', {'medicine': medicine})


@login_required
def delete_medicine(request, medicine_id):
    """Delete a medicine"""
    if request.user.role not in ['ADMIN', 'STORE_MANAGER'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to delete medicines.')
        return redirect('medicines')
    
    if request.method == 'POST':
        medicine = get_object_or_404(Medicine, id=medicine_id)
        medicine_name = medicine.name
        
        # Check if medicine has any prescriptions
        if medicine.prescriptions.exists():
            messages.error(request, f'Cannot delete "{medicine_name}" - it has associated prescriptions.')
            return redirect('medicines')
        
        medicine.delete()
        log_action(request.user, 'DELETE', 'Medicine', medicine_id,
                   f'Deleted medicine: {medicine_name}', request)
        messages.success(request, f'Medicine "{medicine_name}" deleted successfully!')
    
    return redirect('medicines')


@login_required
def add_stock(request, medicine_id):
    if request.user.role not in ['ADMIN', 'STORE_MANAGER'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to add stock.')
        return redirect('medicines')
    
    if request.method == 'POST':
        medicine = get_object_or_404(Medicine, id=medicine_id)
        quantity = request.POST.get('quantity')
        
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


@login_required
def reports_dashboard(request):
    role = request.user.role
    if request.user.is_superuser:
        role = 'ADMIN'
    
    report_type = request.GET.get('type', 'DAILY')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Determine allowed report_for based on role
    allowed_reports = []
    if role == 'ADMIN' or role == 'STORE_MANAGER':
        allowed_reports = [
            ('INVENTORY', 'Inventory'),
            ('PHARMACY', 'Pharmacy'),
            ('LAB', 'Laboratory'),
            ('NURSE', 'Nursing'),
            ('DOCTOR', 'Doctor/Consultation'),
            ('OVERALL', 'Overall Clinic'),
        ]
        report_for = request.GET.get('report_for', 'INVENTORY')
    elif role == 'NURSE':
        # Nurse handles both reception (patient registration) and nursing
        allowed_reports = [('NURSE', 'Nursing & Reception')]
        report_for = 'NURSE'
    elif role == 'DOCTOR':
        allowed_reports = [('DOCTOR', 'Doctor/Consultation')]
        report_for = 'DOCTOR'
    elif role == 'LAB_TECHNICIAN':
        allowed_reports = [('LAB', 'Laboratory')]
        report_for = 'LAB'
    elif role == 'PHARMACIST':
        allowed_reports = [('PHARMACY', 'Pharmacy')]
        report_for = 'PHARMACY'
    else:
        allowed_reports = [('OVERALL', 'Overall Clinic')]
        report_for = 'OVERALL'
    
    today = timezone.now().date()
    
    if not start_date:
        if report_type == 'DAILY':
            start_date = today
        elif report_type == 'WEEKLY':
            start_date = today - timezone.timedelta(days=7)
        else:
            start_date = today.replace(day=1)
    
    if not end_date:
        end_date = today
    
    if isinstance(start_date, str):
        from datetime import datetime
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        from datetime import datetime
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    start_datetime = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
    end_datetime = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.max.time()))
    
    # Generate report data based on report_for
    data = generate_report_data(report_for, start_datetime, end_datetime)
    
    # Save report if requested
    if request.method == 'POST' and 'save_report' in request.POST:
        report = Report.objects.create(
            title=request.POST.get('title', f'{report_type} Report'),
            report_type=report_type,
            report_for=report_for,
            start_date=start_date,
            end_date=end_date,
            data=data,
            generated_by=request.user
        )
        messages.success(request, 'Report saved successfully!')
        return redirect('report_detail', report_id=report.id)
    
    # Get saved reports for this user's department
    saved_reports = Report.objects.filter(
        generated_by=request.user,
        report_for=report_for
    ).order_by('-created_at')[:10]
    
    context = {
        'report_type': report_type,
        'report_for': report_for,
        'start_date': start_date,
        'end_date': end_date,
        'data': data,
        'saved_reports': saved_reports,
        'user_role': role,
        'allowed_reports': allowed_reports,
    }
    return render(request, 'clinic/reports_dashboard.html', context)


@login_required
def report_detail(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    return render(request, 'clinic/report_detail.html', {'report': report})


@login_required
def saved_reports(request):
    reports = Report.objects.filter(generated_by=request.user).order_by('-created_at')
    return render(request, 'clinic/saved_reports.html', {'reports': reports})


def generate_report_data(report_for, start_date, end_date):
    data = {}
    
    if report_for in ['OVERALL', 'RECEPTION']:
        # Reception stats
        data['reception'] = {
            'total_registered': Patient.objects.filter(created_at__gte=start_date, created_at__lte=end_date).count(),
            'total_visits': Visit.objects.filter(visit_date__gte=start_date, visit_date__lte=end_date).count(),
            'students': Visit.objects.filter(visit_date__gte=start_date, visit_date__lte=end_date, patient__patient_type='STUDENT').count(),
            'staff': Visit.objects.filter(visit_date__gte=start_date, visit_date__lte=end_date, patient__patient_type='STAFF').count(),
        }
    
    if report_for in ['OVERALL', 'NURSE']:
        # Nursing stats (includes reception - patient registration)
        data['nurse'] = {
            'total_triages': Triage.objects.filter(created_at__gte=start_date, created_at__lte=end_date).count(),
            'total_registered': Patient.objects.filter(created_at__gte=start_date, created_at__lte=end_date).count(),
            'total_visits': Visit.objects.filter(visit_date__gte=start_date, visit_date__lte=end_date).count(),
        }
    
    if report_for in ['OVERALL', 'DOCTOR']:
        # Doctor stats
        consultations = Consultation.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        data['doctor'] = {
            'total_consultations': consultations.count(),
            'completed_visits': Visit.objects.filter(
                visit_date__gte=start_date, 
                visit_date__lte=end_date,
                status='COMPLETED'
            ).count(),
            'total_prescriptions': Prescription.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date
            ).count(),
        }
    
    if report_for in ['OVERALL', 'LAB']:
        # Lab stats
        labs = LabRequest.objects.filter(date__gte=start_date, date__lte=end_date)
        data['lab'] = {
            'total_tests': labs.count(),
            'completed_tests': labs.filter(status='COMPLETED').count(),
            'pending_tests': labs.filter(status='PENDING').count(),
            'in_progress_tests': labs.filter(status='IN_PROGRESS').count(),
        }
    
    if report_for in ['OVERALL', 'PHARMACY']:
        # Pharmacy stats
        prescriptions = Prescription.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        data['pharmacy'] = {
            'total_prescriptions': prescriptions.count(),
            'dispensed': prescriptions.filter(is_dispensed=True).count(),
            'pending': prescriptions.filter(is_dispensed=False).count(),
        }
    
    if report_for in ['OVERALL', 'INVENTORY', 'PHARMACY']:
        # Inventory stats
        movements = StockMovement.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        data['inventory'] = {
            'total_medicines': Medicine.objects.count(),
            'low_stock': Medicine.objects.filter(stock_quantity__lte=db_models.F('minimum_stock_level'), stock_quantity__gt=0).count(),
            'out_of_stock': Medicine.objects.filter(stock_quantity=0).count(),
            'total_received': movements.filter(movement_type='PURCHASE').aggregate(total=Sum('quantity'))['total'] or 0,
            'total_dispensed': movements.filter(movement_type='DISPENSE').aggregate(total=Sum('quantity'))['total'] or 0,
            'total_movements': movements.count(),
        }
    
    # Summary
    data['summary'] = {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    }
    
    return data
