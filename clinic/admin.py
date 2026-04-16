from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.template.response import TemplateResponse
from django.urls import path
from .models import (
    User, Patient, Visit, Triage, Consultation, Prescription,
    Medicine, StockMovement, LabRequest, LabTestType, Notification, DailyReport, AuditLog
)


class ClinicAdminSite(admin.AdminSite):
    site_header = 'Kumi University Clinic'
    site_title = 'Clinic Admin'
    index_title = 'Dashboard'
    login_template = 'admin/login.html'
    
    def index(self, request, extra_context=None):
        from .models import Patient, Visit, Medicine, LabRequest, Prescription
        from django.db.models import F
        from django.utils import timezone
        
        today = timezone.now().date()
        
        try:
            low_stock_count = Medicine.objects.filter(
                stock_quantity__lt=F('minimum_stock_level')
            ).count()
        except Exception:
            low_stock_count = 0
        
        stats = {
            'total_patients': Patient.objects.count(),
            'today_visits': Visit.objects.filter(visit_date=today).count(),
            'total_medicines': Medicine.objects.count(),
            'pending_labs': LabRequest.objects.filter(status='PENDING').count(),
            'pending_prescriptions': Prescription.objects.filter(is_dispensed=False).count(),
            'low_stock_medicines': low_stock_count,
        }
        
        recent_visits = Visit.objects.select_related('patient', 'created_by').order_by('-visit_date')[:5]
        
        extra_context = extra_context or {}
        extra_context.update({
            'stats': stats,
            'recent_visits': recent_visits,
        })
        return super().index(request, extra_context)
    
    def login(self, request, extra_context=None):
        from django.contrib.auth.views import LoginView
        return LoginView.as_view(template_name=self.login_template, extra_context=extra_context)(request)
    
    def get_urls(self):
        from django.urls import include
        urls = super().get_urls()
        return urls


clinic_admin_site = ClinicAdminSite(name='clinic_admin')


@admin.register(LabTestType, site=clinic_admin_site)
class LabTestTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(User, site=clinic_admin_site)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone', 'department')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'role', 'phone', 'department'),
        }),
    )


@admin.register(Patient, site=clinic_admin_site)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'university_id', 'patient_type', 'department', 'phone', 'gender', 'created_at']
    list_filter = ['patient_type', 'gender', 'department']
    search_fields = ['full_name', 'university_id', 'phone', 'department']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at']


class TriageInline(admin.StackedInline):
    model = Triage
    extra = 0
    readonly_fields = ['created_at', 'updated_at']


class ConsultationInline(admin.StackedInline):
    model = Consultation
    extra = 0
    readonly_fields = ['created_at', 'updated_at']


class LabRequestInline(admin.TabularInline):
    model = LabRequest
    extra = 0
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Visit, site=clinic_admin_site)
class VisitAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'visit_date', 'status', 'created_by']
    list_filter = ['status', 'visit_date', 'patient__patient_type']
    search_fields = ['patient__full_name', 'patient__university_id', 'reason_for_visit']
    date_hierarchy = 'visit_date'
    readonly_fields = ['created_at', 'updated_at']
    inlines = [TriageInline, ConsultationInline, LabRequestInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('patient', 'created_by')


@admin.register(Triage, site=clinic_admin_site)
class TriageAdmin(admin.ModelAdmin):
    list_display = ['visit', 'temperature', 'blood_pressure', 'weight', 'recorded_by', 'created_at']
    search_fields = ['visit__patient__full_name', 'symptoms']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(Consultation, site=clinic_admin_site)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ['visit', 'doctor', 'diagnosis', 'created_at']
    search_fields = ['visit__patient__full_name', 'diagnosis', 'doctor__username']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


class PrescriptionInline(admin.TabularInline):
    model = Prescription
    extra = 0
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Prescription, site=clinic_admin_site)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ['medicine', 'consultation', 'dosage', 'quantity', 'is_dispensed', 'created_at']
    list_filter = ['is_dispensed', 'medicine__category']
    search_fields = ['medicine__name', 'consultation__visit__patient__full_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Medicine, site=clinic_admin_site)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'stock_quantity', 'unit', 'supplier', 'minimum_stock_level', 'is_low_stock']
    list_filter = ['category', 'supplier']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['stock_quantity']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'unit')
        }),
        ('Stock Information', {
            'fields': ('stock_quantity', 'minimum_stock_level', 'location')
        }),
        ('Supplier Information', {
            'fields': ('supplier', 'supplier_contact')
        }),
    )
    
    def is_low_stock(self, obj):
        return obj.is_low_stock
    is_low_stock.boolean = True


@admin.register(StockMovement, site=clinic_admin_site)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['medicine', 'movement_type', 'quantity', 'performed_by', 'date']
    list_filter = ['movement_type', 'date', 'medicine__category']
    search_fields = ['medicine__name', 'performed_by__username']
    date_hierarchy = 'date'
    readonly_fields = ['created_at']


@admin.register(LabRequest, site=clinic_admin_site)
class LabRequestAdmin(admin.ModelAdmin):
    list_display = ['visit', 'test_name', 'status', 'requested_by', 'technician', 'date']
    list_filter = ['status', 'test_name', 'date']
    search_fields = ['visit__patient__full_name', 'test_name']
    date_hierarchy = 'date'
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Notification, site=clinic_admin_site)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'user', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['title', 'message', 'user__username']
    date_hierarchy = 'created_at'


@admin.register(DailyReport, site=clinic_admin_site)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ['report_date', 'total_patients', 'students_count', 'staff_count', 'completed_visits']
    list_filter = ['report_date']
    date_hierarchy = 'report_date'
    readonly_fields = ['created_at']


@admin.register(AuditLog, site=clinic_admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'model_name', 'description', 'ip_address']
    list_filter = ['action', 'model_name', 'timestamp']
    search_fields = ['user__username', 'description', 'model_name']
    date_hierarchy = 'timestamp'
    readonly_fields = ['timestamp']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
