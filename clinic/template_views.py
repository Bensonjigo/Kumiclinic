from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import models as db_models
from django.db.models import Count
from .models import (
    Patient, Visit, Triage, Consultation, Prescription,
    Medicine, LabRequest, DailyReport, User
)


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Invalid credentials')
    return render(request, 'clinic/login.html')


def logout_view(request):
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
    total_prescriptions = sum(v.consultation.prescriptions.count() for v in visits if v.consultation)
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
        gender = request.POST.get('gender')
        date_of_birth = request.POST.get('date_of_birth')
        
        if Patient.objects.filter(university_id=university_id).exists():
            messages.error(request, 'A patient with this university ID already exists.')
            return redirect('register_patient')
        
        patient = Patient.objects.create(
            full_name=full_name,
            patient_type=patient_type,
            university_id=university_id,
            department=department,
            phone=phone,
            gender=gender,
            date_of_birth=date_of_birth
        )
        messages.success(request, f'Patient {patient.full_name} registered successfully!')
        return redirect('dashboard')
    
    return render(request, 'clinic/register_patient.html')


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
        
        patient = get_object_or_404(Patient, id=patient_id)
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
    
    if request.method == 'POST':
        consultation = Consultation.objects.create(
            visit=visit,
            doctor=request.user,
            diagnosis=request.POST.get('diagnosis'),
            doctor_notes=request.POST.get('doctor_notes'),
            treatment_plan=request.POST.get('treatment_plan')
        )
        
        medicine_id = request.POST.get('medicine')
        dosage = request.POST.get('dosage')
        quantity = request.POST.get('quantity')
        
        if medicine_id and quantity:
            try:
                quantity = int(quantity)
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
    
    messages.success(request, f'Dispensed {prescription.quantity} {medicine.unit} of {medicine.name}')
    return redirect('pending_prescriptions')


@login_required
def medicines_list(request):
    medicines = Medicine.objects.all().order_by('name')
    return render(request, 'clinic/medicines.html', {'medicines': medicines})


@login_required
def reports_list(request):
    reports = DailyReport.objects.all().order_by('-report_date')[:30]
    return render(request, 'clinic/reports.html', {'reports': reports})
