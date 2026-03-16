from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.db import models as db_models
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from django.contrib import messages
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.authtoken.models import Token

from .models import (
    Patient, Visit, Triage, Consultation, Prescription,
    Medicine, StockMovement, LabRequest, Notification, DailyReport
)


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    """Custom CSRF failure handler - redirects to login with friendly message"""
    from django.http import HttpResponseRedirect
    from django.urls import reverse
    
    # If user is authenticated, show a friendly message and redirect back
    if request.user.is_authenticated:
        messages.error(request, "Your session may have expired. Please try again.")
        return HttpResponseRedirect(reverse('dashboard'))
    
    # If not authenticated, redirect to login
    messages.error(request, "Please log in to continue.")
    return HttpResponseRedirect(reverse('login') + '?next=' + request.path)


User = get_user_model()
from .serializers import (
    UserSerializer, UserCreateSerializer, PatientSerializer, PatientCreateSerializer,
    VisitListSerializer, VisitDetailSerializer, VisitCreateSerializer, VisitStatusUpdateSerializer,
    TriageSerializer, ConsultationSerializer, ConsultationCreateSerializer,
    PrescriptionSerializer, MedicineSerializer, MedicineCreateSerializer,
    StockMovementSerializer, StockMovementCreateSerializer,
    LabRequestSerializer, LabRequestCreateSerializer, LabResultSerializer,
    NotificationSerializer, DashboardStatsSerializer, DailyReportSerializer
)


class IsReceptionistOrReadOnly(IsAuthenticated):
    def has_permission(self, request, view):
        if request.method in ['GET']:
            return True
        return request.user.is_authenticated and (request.user.is_receptionist or request.user.is_superuser)


class IsNurseOrReadOnly(IsAuthenticated):
    def has_permission(self, request, view):
        if request.method in ['GET']:
            return True
        return request.user.is_authenticated and (request.user.is_nurse or request.user.is_superuser)


class IsDoctorOrReadOnly(IsAuthenticated):
    def has_permission(self, request, view):
        if request.method in ['GET']:
            return True
        return request.user.is_authenticated and (request.user.is_doctor or request.user.is_superuser)


class IsAdminOrReadOnly(IsAuthenticated):
    def has_permission(self, request, view):
        if request.method in ['GET']:
            return True
        return request.user.is_authenticated and (request.user.role == 'ADMIN' or request.user.is_superuser)


class CanAccessPatients(IsAuthenticated):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['RECEPTIONIST', 'NURSE', 'DOCTOR', 'ADMIN'] or request.user.is_superuser


class CanAccessVisits(IsAuthenticated):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['RECEPTIONIST', 'NURSE', 'DOCTOR', 'LAB_TECHNICIAN', 'PHARMACIST', 'ADMIN'] or request.user.is_superuser


class CanAccessPrescriptions(IsAuthenticated):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['DOCTOR', 'PHARMACIST', 'ADMIN'] or request.user.is_superuser


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'email']
    filterset_fields = ['role', 'is_active']
    ordering_fields = ['username', 'date_joined']
    ordering = ['username']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            if self.request.user.is_authenticated and self.request.user.is_superuser:
                return [IsAuthenticated()]
            return [IsAdminUser()]
        return super().get_permissions()
    
    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionError("Only administrators can create users")
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    from django.contrib.auth import authenticate
    from django.contrib.auth.signals import user_login_failed
    from django.core.cache import cache
    from django.conf import settings
    
    username = request.data.get('username')
    password = request.data.get('password')
    
    rate_limit_key = f'login_attempt_{request.META.get("REMOTE_ADDR", "unknown")}'
    attempt_count = cache.get(rate_limit_key, 0)
    
    if attempt_count >= 5:
        return Response(
            {'error': 'Too many login attempts. Please try again in 5 minutes.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    if username and password:
        user = authenticate(username=username, password=password)
        if user:
            cache.delete(rate_limit_key)
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            })
        else:
            cache.set(rate_limit_key, attempt_count + 1, 300)
    
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    request.user.auth_token.delete()
    return Response({'message': 'Logged out successfully'})


class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [CanAccessPatients]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['full_name', 'university_id', 'phone', 'department']
    filterset_fields = ['patient_type', 'gender']
    ordering_fields = ['full_name', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PatientCreateSerializer
        return PatientSerializer
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '')
        patients = Patient.objects.filter(
            Q(full_name__icontains=query) | 
            Q(university_id__icontains=query) |
            Q(phone__icontains=query)
        )[:10]
        serializer = self.get_serializer(patients, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def autocomplete(self, request):
        query = request.query_params.get('q', '')
        patients = Patient.objects.filter(
            Q(full_name__icontains=query) | 
            Q(university_id__icontains=query)
        )[:10]
        data = [{'id': p.id, 'name': p.full_name, 'university_id': p.university_id, 'type': p.get_patient_type_display()} for p in patients]
        return Response(data)


class VisitViewSet(viewsets.ModelViewSet):
    queryset = Visit.objects.select_related('patient', 'created_by', 'triage', 'consultation').prefetch_related('lab_requests', 'consultation__prescriptions').all()
    serializer_class = VisitListSerializer
    permission_classes = [CanAccessVisits]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'patient__patient_type']
    search_fields = ['patient__full_name', 'patient__university_id', 'reason_for_visit']
    ordering_fields = ['visit_date', 'status', 'created_at']
    ordering = ['-visit_date']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return VisitListSerializer
        if self.action == 'retrieve':
            return VisitDetailSerializer
        if self.action == 'create':
            return VisitCreateSerializer
        return VisitListSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        today = self.request.query_params.get('today', '').lower() == 'true'
        if today:
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            queryset = queryset.filter(visit_date__gte=today_start)
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        visit = serializer.save()
        return Response(VisitDetailSerializer(visit).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        visit = self.get_object()
        serializer = VisitStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        
        if not visit.can_update_to(new_status):
            return Response(
                {'error': f'Cannot transition from {visit.get_status_display()} to {new_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        visit.update_status(new_status)
        return Response(VisitListSerializer(visit).data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        today = timezone.now().date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        
        total_today = Visit.objects.filter(visit_date__gte=today_start).count()
        waiting = Visit.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
        
        return Response({
            'total_patients_today': total_today,
            'patients_waiting': waiting,
        })
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        today = timezone.now().date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        
        total_today = Visit.objects.filter(visit_date__gte=today_start).count()
        patients_waiting = Visit.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
        low_stock = Medicine.objects.filter(stock_quantity__lte=db_models.F('minimum_stock_level')).count()
        pending_labs = LabRequest.objects.filter(status='PENDING').count()
        completed_today = Visit.objects.filter(
            visit_date__gte=today_start,
            status='COMPLETED'
        ).count()
        
        data = {
            'total_patients_today': total_today,
            'patients_waiting': patients_waiting,
            'low_stock_items': low_stock,
            'pending_lab_tests': pending_labs,
            'completed_today': completed_today,
        }
        return Response(DashboardStatsSerializer(data).data)


class TriageViewSet(viewsets.ModelViewSet):
    queryset = Triage.objects.all()
    serializer_class = TriageSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        triage = serializer.save(recorded_by=self.request.user)
        visit = triage.visit
        visit.update_status('WAITING_FOR_DOCTOR')
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        visits = Visit.objects.filter(status='WAITING_FOR_TRIAGE')
        serializer = VisitListSerializer(visits, many=True)
        return Response(serializer.data)


class ConsultationViewSet(viewsets.ModelViewSet):
    queryset = Consultation.objects.all()
    serializer_class = ConsultationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ConsultationCreateSerializer
        return ConsultationSerializer
    
    def perform_create(self, serializer):
        consultation = serializer.save(doctor=self.request.user)
        visit = consultation.visit
        visit.update_status('WAITING_FOR_PHARMACY')
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        visits = Visit.objects.filter(status='WAITING_FOR_DOCTOR')
        serializer = VisitListSerializer(visits, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_prescription(self, request, pk=None):
        consultation = self.get_object()
        serializer = PrescriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(consultation=consultation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def add_lab_request(self, request, pk=None):
        consultation = self.get_object()
        serializer = LabRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lab_request = serializer.save(
            requested_by=self.request.user,
            visit=consultation.visit
        )
        consultation.visit.update_status('IN_LAB')
        return Response(LabRequestSerializer(lab_request).data, status=status.HTTP_201_CREATED)


class PrescriptionViewSet(viewsets.ModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_dispensed', 'medicine']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    @action(detail=True, methods=['post'])
    def dispense(self, request, pk=None):
        prescription = self.get_object()
        
        if prescription.is_dispensed:
            return Response({'error': 'Already dispensed'}, status=status.HTTP_400_BAD_REQUEST)
        
        medicine = prescription.medicine
        if medicine.stock_quantity < prescription.quantity:
            return Response(
                {'error': f'Insufficient stock. Available: {medicine.stock_quantity}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        StockMovement.objects.create(
            medicine=medicine,
            movement_type='DISPENSE',
            quantity=prescription.quantity,
            performed_by=request.user,
            notes=f"Dispensed for Visit #{prescription.consultation.visit_id}"
        )
        
        prescription.is_dispensed = True
        prescription.save()
        
        return Response(PrescriptionSerializer(prescription).data)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        prescriptions = Prescription.objects.filter(is_dispensed=False)
        serializer = self.get_serializer(prescriptions, many=True)
        return Response(serializer.data)


class MedicineViewSet(viewsets.ModelViewSet):
    queryset = Medicine.objects.all()
    serializer_class = MedicineSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'category']
    filterset_fields = ['category', 'is_low_stock', 'is_expired']
    ordering_fields = ['name', 'stock_quantity', 'expiry_date']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return MedicineCreateSerializer
        return MedicineSerializer
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        medicines = Medicine.objects.filter(
            stock_quantity__lte=db_models.F('minimum_stock_level')
        )
        serializer = self.get_serializer(medicines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def expired(self, request):
        today = timezone.now().date()
        medicines = Medicine.objects.filter(expiry_date__lt=today)
        serializer = self.get_serializer(medicines, many=True)
        return Response(serializer.data)


class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = StockMovement.objects.all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['medicine', 'movement_type']
    ordering_fields = ['date']
    ordering = ['-date']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StockMovementCreateSerializer
        return StockMovementSerializer
    
    def perform_create(self, serializer):
        serializer.save(performed_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        medicine_id = request.query_params.get('medicine_id')
        if medicine_id:
            movements = StockMovement.objects.filter(medicine_id=medicine_id)
        else:
            movements = StockMovement.objects.all()
        
        page = self.paginate_queryset(movements)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(movements, many=True)
        return Response(serializer.data)


class LabRequestViewSet(viewsets.ModelViewSet):
    queryset = LabRequest.objects.all()
    serializer_class = LabRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'test_name', 'visit']
    ordering_fields = ['date', 'status']
    ordering = ['-date']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return LabRequestCreateSerializer
        if self.action in ['update', 'partial_update']:
            return LabResultSerializer
        return LabRequestSerializer
    
    def perform_create(self, serializer):
        lab_request = serializer.save(requested_by=self.request.user)
        lab_request.visit.update_status('IN_LAB')
    
    def perform_update(self, serializer):
        lab_request = serializer.save(
            technician=self.request.user,
            completed_date=timezone.now() if serializer.validated_data.get('status') == 'COMPLETED' else None
        )
        if lab_request.status == 'COMPLETED':
            lab_request.visit.update_status('WAITING_FOR_DOCTOR')
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        lab_requests = LabRequest.objects.filter(status='PENDING')
        serializer = self.get_serializer(lab_requests, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_tests(self, request):
        lab_requests = LabRequest.objects.filter(requested_by=request.user)
        serializer = self.get_serializer(lab_requests, many=True)
        return Response(serializer.data)


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        notifications = Notification.objects.filter(user=request.user, is_read=False)
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(NotificationSerializer(notification).data)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read'})


class DailyReportViewSet(viewsets.ModelViewSet):
    queryset = DailyReport.objects.all()
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ['report_date']
    ordering = ['-report_date']
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        from django.db import models as db_models
        today = timezone.now().date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))
        
        visits_today = Visit.objects.filter(visit_date__gte=today_start, visit_date__lte=today_end)
        
        students = visits_today.filter(patient__patient_type='STUDENT').count()
        staff = visits_today.filter(patient__patient_type='STAFF').count()
        completed = visits_today.filter(status='COMPLETED').count()
        
        lab_tests = LabRequest.objects.filter(date__gte=today_start, date__lte=today_end, status='COMPLETED').count()
        
        prescriptions = Prescription.objects.filter(
            consultation__visit__visit_date__gte=today_start,
            consultation__visit__visit_date__lte=today_end,
            is_dispensed=True
        ).count()
        
        report, created = DailyReport.objects.get_or_create(
            report_date=today,
            defaults={
                'total_patients': visits_today.count(),
                'students_count': students,
                'staff_count': staff,
                'completed_visits': completed,
                'lab_tests_conducted': lab_tests,
                'medicines_dispensed': prescriptions,
            }
        )
        
        if not created:
            report.total_patients = visits_today.count()
            report.students_count = students
            report.staff_count = staff
            report.completed_visits = completed
            report.lab_tests_conducted = lab_tests
            report.medicines_dispensed = prescriptions
            report.save()
        
        return Response(DailyReportSerializer(report).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_data_view(request, visit_id):
    visit = get_object_or_404(Visit, id=visit_id)
    patient = visit.patient
    
    user = request.user
    
    if not (user.is_superuser or 
            user.role == 'ADMIN' or
            user.role == 'RECEPTIONIST' or
            user.role == 'NURSE' or
            user.role == 'DOCTOR' or
            user.role == 'LAB_TECHNICIAN' or
            user.role == 'PHARMACIST'):
        return Response(
            {'error': 'You do not have permission to view this patient data'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    all_visits = Visit.objects.filter(patient=patient).prefetch_related(
        'consultation__prescriptions__medicine', 'lab_requests'
    ).order_by('-visit_date')
    
    medical_history_html = ''
    for v in all_visits[:10]:
        try:
            consultation = v.consultation
            if consultation:
                medical_history_html += f'''
                <div class="border-b py-3">
                    <div class="flex justify-between items-start mb-1">
                        <span class="font-medium">{v.visit_date.strftime('%d %b %Y')}</span>
                        <span class="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">{consultation.diagnosis}</span>
                    </div>
                    <p class="text-sm text-gray-600">{consultation.doctor_notes or 'No notes'}</p>
                </div>
                '''
        except Exception:
            pass
    if not medical_history_html:
        medical_history_html = '<p class="text-gray-500 text-sm">No medical history found</p>'
    
    lab_results_html = ''
    lab_requests = LabRequest.objects.filter(visit__patient=patient).select_related('visit').order_by('-date')[:10]
    for lab in lab_requests:
        status_class = 'bg-gray-100 text-gray-800'
        if lab.status == 'COMPLETED':
            status_class = 'bg-green-100 text-green-800'
        elif lab.status == 'IN_PROGRESS':
            status_class = 'bg-yellow-100 text-yellow-800'
        elif lab.status == 'PENDING':
            status_class = 'bg-blue-100 text-blue-800'
        
        result_display = lab.result if lab.result else 'No result recorded'
        date_display = lab.completed_date.strftime('%d %b %Y') if lab.completed_date else (lab.date.strftime('%d %b %Y') if lab.date else '')
        
        lab_results_html += f'''
        <div class="border-b py-3">
            <div class="flex justify-between items-start mb-1">
                <span class="font-medium">{lab.get_test_name_display()}</span>
                <span class="text-xs {status_class} px-2 py-0.5 rounded">{lab.get_status_display()}</span>
            </div>
            <p class="text-sm text-gray-600">{result_display}</p>
            <p class="text-xs text-gray-400">{date_display}</p>
        </div>
        '''
    if not lab_results_html:
        lab_results_html = '<p class="text-gray-500 text-sm">No lab results found</p>'
    
    medications_html = ''
    prescriptions = Prescription.objects.filter(consultation__visit__patient=patient).select_related('medicine', 'consultation__visit').order_by('-consultation__visit__visit_date')[:10]
    for rx in prescriptions:
        dispensed_class = 'bg-purple-100 text-purple-800' if rx.is_dispensed else 'bg-yellow-100 text-yellow-800'
        medications_html += f'''
        <div class="border-b py-3">
            <div class="flex justify-between items-start mb-1">
                <span class="font-medium">{rx.medicine.name}</span>
                <span class="text-xs {dispensed_class} px-2 py-0.5 rounded">{"Dispensed" if rx.is_dispensed else "Pending"}</span>
            </div>
            <p class="text-sm text-gray-600">{rx.dosage or 'No dosage'}</p>
            <p class="text-xs text-gray-400">Qty: {rx.quantity}</p>
        </div>
        '''
    if not medications_html:
        medications_html = '<p class="text-gray-500 text-sm">No medications found</p>'
    
    visit_notes_html = ''
    try:
        consultation = visit.consultation
        if consultation:
            visit_notes_html = f'''
            <div class="space-y-4">
                <div>
                    <label class="font-medium text-sm text-gray-500">Diagnosis</label>
                    <p class="text-gray-900">{consultation.diagnosis}</p>
                </div>
                <div>
                    <label class="font-medium text-sm text-gray-500">Treatment Plan</label>
                    <p class="text-gray-900">{consultation.treatment_plan or 'No treatment plan'}</p>
                </div>
                <div>
                    <label class="font-medium text-sm text-gray-500">Doctor Notes</label>
                    <p class="text-gray-900">{consultation.doctor_notes or 'No notes'}</p>
                </div>
            </div>
            '''
        else:
            visit_notes_html = '<p class="text-gray-500 text-sm">No consultation notes yet</p>'
    except Exception:
        visit_notes_html = '<p class="text-gray-500 text-sm">No consultation notes yet</p>'
    
    return Response({
        'medical_history': medical_history_html,
        'lab_results': lab_results_html,
        'medications': medications_html,
        'visit_notes': visit_notes_html,
    })
