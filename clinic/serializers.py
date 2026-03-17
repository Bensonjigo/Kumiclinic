from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Patient, Visit, Triage, Consultation, Prescription,
    Medicine, StockMovement, LabRequest, Notification, DailyReport
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name', 
                  'role', 'phone', 'department', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=12, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 
                  'role', 'phone', 'department']
    
    def create(self, validated_data):
        validated_data.pop('is_staff', None)
        validated_data.pop('is_superuser', None)
        validated_data.pop('is_active', None)
        validated_data.pop('groups', None)
        validated_data.pop('user_permissions', None)
        
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class PatientSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()
    visit_count = serializers.SerializerMethodField()
    last_visit = serializers.SerializerMethodField()
    
    class Meta:
        model = Patient
        fields = ['id', 'full_name', 'patient_type', 'university_id', 'department', 
                  'phone', 'gender', 'date_of_birth', 'age', 'created_at', 
                  'visit_count', 'last_visit']
        read_only_fields = ['id', 'created_at']
    
    def get_visit_count(self, obj):
        return obj.visits.count()
    
    def get_last_visit(self, obj):
        last = obj.visits.first()
        return VisitListSerializer(last).data if last else None


class PatientCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ['id', 'full_name', 'patient_type', 'university_id', 'department', 
                  'phone', 'gender', 'date_of_birth']
    
    def validate_university_id(self, value):
        if Patient.objects.filter(university_id=value).exists():
            raise serializers.ValidationError("A patient with this university ID already exists.")
        return value


class TriageSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Triage
        fields = ['id', 'visit', 'temperature', 'blood_pressure', 'weight', 'heart_rate',
                  'symptoms', 'nurse_notes', 'recorded_by', 'recorded_by_name', 
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_recorded_by_name(self, obj):
        return obj.recorded_by.get_full_name() if obj.recorded_by else None


class PrescriptionSerializer(serializers.ModelSerializer):
    medicine_name = serializers.SerializerMethodField()
    is_dispensed = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Prescription
        fields = ['id', 'consultation', 'medicine', 'medicine_name', 'dosage', 
                  'quantity', 'notes', 'is_dispensed', 'created_at', 'updated_at']
        read_only_fields = ['id', 'is_dispensed', 'created_at', 'updated_at']
    
    def get_medicine_name(self, obj):
        return obj.medicine.name


class ConsultationSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    prescriptions = PrescriptionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Consultation
        fields = ['id', 'visit', 'doctor', 'doctor_name', 'diagnosis', 'doctor_notes',
                  'treatment_plan', 'prescriptions', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_doctor_name(self, obj):
        return obj.doctor.get_full_name() if obj.doctor else None


class ConsultationCreateSerializer(serializers.ModelSerializer):
    prescriptions = PrescriptionSerializer(many=True, required=False)
    
    class Meta:
        model = Consultation
        fields = ['visit', 'diagnosis', 'doctor_notes', 'treatment_plan', 'prescriptions']
    
    def create(self, validated_data):
        prescriptions_data = validated_data.pop('prescriptions', [])
        consultation = Consultation.objects.create(**validated_data)
        for prescription_data in prescriptions_data:
            Prescription.objects.create(consultation=consultation, **prescription_data)
        return consultation


class LabRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    technician_name = serializers.SerializerMethodField()
    test_display = serializers.SerializerMethodField()
    
    class Meta:
        model = LabRequest
        fields = ['id', 'visit', 'test_name', 'test_display', 'custom_test_name', 'status',
                  'requested_by', 'requested_by_name', 'technician', 'technician_name',
                  'result', 'notes', 'date', 'completed_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_requested_by_name(self, obj):
        return obj.requested_by.get_full_name() if obj.requested_by else None
    
    def get_technician_name(self, obj):
        return obj.technician.get_full_name() if obj.technician else None
    
    def get_test_display(self, obj):
        return obj.get_test_name_display()


class LabRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabRequest
        fields = ['visit', 'test_name', 'custom_test_name', 'notes']


class LabResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabRequest
        fields = ['status', 'result', 'notes', 'technician', 'completed_date']


class VisitListSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()
    patient_university_id = serializers.SerializerMethodField()
    patient_type = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    triage = TriageSerializer(read_only=True)
    consultation = ConsultationSerializer(read_only=True)
    lab_requests_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Visit
        fields = ['id', 'patient', 'patient_name', 'patient_university_id', 'patient_type',
                  'visit_date', 'reason_for_visit', 'status', 'created_by', 'created_by_name',
                  'triage', 'consultation', 'lab_requests_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_patient_name(self, obj):
        return obj.patient.full_name
    
    def get_patient_university_id(self, obj):
        return obj.patient.university_id
    
    def get_patient_type(self, obj):
        return obj.patient.get_patient_type_display()
    
    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None
    
    def get_lab_requests_count(self, obj):
        return obj.lab_requests.count()


class VisitDetailSerializer(VisitListSerializer):
    patient = PatientSerializer(read_only=True)
    lab_requests = LabRequestSerializer(many=True, read_only=True)
    
    class Meta(VisitListSerializer.Meta):
        fields = VisitListSerializer.Meta.fields + ['patient', 'lab_requests']


class VisitCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = ['patient', 'reason_for_visit']
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        validated_data['status'] = 'WAITING_FOR_TRIAGE'
        return super().create(validated_data)


class VisitStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[s[0] for s in Visit.STATUS_CHOICES])


class MedicineSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    category_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Medicine
        fields = ['id', 'name', 'category', 'category_display', 'stock_quantity', 'unit',
                  'expiry_date', 'minimum_stock_level', 'is_low_stock', 'is_expired',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_category_display(self, obj):
        return obj.get_category_display()


class MedicineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicine
        fields = ['name', 'category', 'stock_quantity', 'unit', 'expiry_date', 'minimum_stock_level']


class StockMovementSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.SerializerMethodField()
    medicine_name = serializers.SerializerMethodField()
    
    class Meta:
        model = StockMovement
        fields = ['id', 'medicine', 'medicine_name', 'movement_type', 'quantity',
                  'performed_by', 'performed_by_name', 'notes', 'date', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_performed_by_name(self, obj):
        return obj.performed_by.get_full_name() if obj.performed_by else None
    
    def get_medicine_name(self, obj):
        return obj.medicine.name


class StockMovementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = ['medicine', 'movement_type', 'quantity', 'notes']
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'notification_type', 'is_read', 
                  'user', 'created_at']
        read_only_fields = ['id', 'created_at']


class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = ['id', 'report_date', 'total_patients', 'students_count', 'staff_count',
                  'completed_visits', 'lab_tests_conducted', 'medicines_dispensed', 'created_at']
        read_only_fields = ['id', 'created_at']


class DashboardStatsSerializer(serializers.Serializer):
    total_patients_today = serializers.IntegerField()
    patients_waiting = serializers.IntegerField()
    low_stock_items = serializers.IntegerField()
    pending_lab_tests = serializers.IntegerField()
    completed_today = serializers.IntegerField()
