from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = [
        ('RECEPTIONIST', 'Receptionist'),
        ('NURSE', 'Nurse'),
        ('DOCTOR', 'Doctor'),
        ('LAB_TECHNICIAN', 'Lab Technician'),
        ('PHARMACIST', 'Pharmacist'),
        ('STORE_MANAGER', 'Store Manager'),
        ('ADMIN', 'Admin'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='RECEPTIONIST')
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    @property
    def is_store_manager(self):
        return self.role == 'STORE_MANAGER' or self.is_superuser
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
    
    @property
    def is_receptionist(self):
        return self.role == 'RECEPTIONIST' or self.is_superuser
    
    @property
    def is_nurse(self):
        return self.role == 'NURSE' or self.is_superuser
    
    @property
    def is_doctor(self):
        return self.role == 'DOCTOR' or self.is_superuser
    
    @property
    def is_lab_technician(self):
        return self.role == 'LAB_TECHNICIAN' or self.is_superuser
    
    @property
    def is_pharmacist(self):
        return self.role == 'PHARMACIST' or self.is_superuser
    
    @property
    def is_admin(self):
        return self.role == 'ADMIN' or self.is_superuser


class Patient(models.Model):
    PATIENT_TYPE_CHOICES = [
        ('STUDENT', 'Student'),
        ('STAFF', 'Staff'),
    ]
    
    GENDER_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
    ]
    
    full_name = models.CharField(max_length=200)
    patient_type = models.CharField(max_length=10, choices=PATIENT_TYPE_CHOICES)
    university_id = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    date_of_birth = models.DateField()
    
    # Next of Kin
    next_of_kin_name = models.CharField(max_length=200, blank=True, null=True)
    next_of_kin_relationship = models.CharField(max_length=50, blank=True, null=True)
    next_of_kin_contact = models.CharField(max_length=20, blank=True, null=True)
    next_of_kin_address = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} ({self.university_id})"
    
    @property
    def age(self):
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Visit(models.Model):
    STATUS_CHOICES = [
        ('REGISTERED', 'Registered'),
        ('WAITING_FOR_TRIAGE', 'Waiting for Triage'),
        ('WAITING_FOR_DOCTOR', 'Waiting for Doctor'),
        ('IN_LAB', 'In Lab'),
        ('WAITING_FOR_PHARMACY', 'Waiting for Pharmacy'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    visit_date = models.DateTimeField(default=timezone.now)
    reason_for_visit = models.TextField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='REGISTERED')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_visits')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-visit_date']
    
    def __str__(self):
        return f"Visit #{self.id} - {self.patient.full_name} ({self.get_status_display()})"
    
    def can_update_to(self, new_status):
        transitions = {
            'REGISTERED': ['WAITING_FOR_TRIAGE', 'CANCELLED'],
            'WAITING_FOR_TRIAGE': ['WAITING_FOR_DOCTOR', 'CANCELLED'],
            'WAITING_FOR_DOCTOR': ['IN_LAB', 'WAITING_FOR_PHARMACY', 'CANCELLED'],
            'IN_LAB': ['WAITING_FOR_PHARMACY', 'WAITING_FOR_DOCTOR'],
            'WAITING_FOR_PHARMACY': ['COMPLETED'],
            'COMPLETED': [],
            'CANCELLED': [],
        }
        return new_status in transitions.get(self.status, [])
    
    def update_status(self, new_status):
        if self.can_update_to(new_status):
            self.status = new_status
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False


class Triage(models.Model):
    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='triage')
    temperature = models.DecimalField(max_digits=4, decimal_places=1, help_text="Temperature in Celsius", null=True, blank=True)
    blood_pressure = models.CharField(max_length=20, help_text="e.g., 120/80", null=True, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, help_text="Weight in kg", null=True, blank=True)
    heart_rate = models.IntegerField(help_text="Beats per minute", null=True, blank=True)
    symptoms = models.TextField(blank=True)
    nurse_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_triages')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Triage for Visit #{self.visit_id}"


class Consultation(models.Model):
    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='consultation')
    doctor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='consultations')
    diagnosis = models.TextField()
    doctor_notes = models.TextField(blank=True)
    treatment_plan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Consultation for Visit #{self.visit_id}"


class Medicine(models.Model):
    CATEGORY_CHOICES = [
        ('TABLET', 'Tablet'),
        ('CAPSULE', 'Capsule'),
        ('SYRUP', 'Syrup'),
        ('INJECTION', 'Injection'),
        ('CREAM', 'Cream'),
        ('OINTMENT', 'Ointment'),
        ('DROP', 'Drop'),
        ('SOLUTION', 'Solution'),
        ('OTHER', 'Other'),
    ]
    
    SUPPLIER_CHOICES = [
        ('JMS', 'JMS Pharmaceuticals'),
        ('PHARMACCESS', 'PharmAccess'),
        ('SPS', 'SPS Pharmaceuticals'),
        ('ABU', 'Abu Pharmaceutical'),
        ('LOCAL', 'Local Supplier'),
        ('OTHER', 'Other'),
    ]
    
    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    stock_quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, help_text="e.g., tablets, ml, bottles")
    minimum_stock_level = models.PositiveIntegerField(default=10)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supplier = models.CharField(max_length=50, choices=SUPPLIER_CHOICES, blank=True)
    supplier_contact = models.CharField(max_length=200, blank=True, help_text="Supplier contact info")
    location = models.CharField(max_length=100, blank=True, help_text="Storage location e.g., Shelf A-1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock_level
    
    @property
    def status(self):
        if self.stock_quantity == 0:
            return 'OUT_OF_STOCK'
        elif self.is_low_stock:
            return 'LOW_STOCK'
        return 'IN_STOCK'


class Prescription(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='prescriptions')
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='prescriptions')
    dosage = models.CharField(max_length=100, help_text="e.g., 2 tablets thrice daily")
    quantity = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    is_dispensed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.medicine.name} - {self.quantity} {self.medicine.unit}"


class StockMovement(models.Model):
    MOVEMENT_TYPE_CHOICES = [
        ('PURCHASE', 'Purchase'),
        ('DISPENSE', 'Dispense'),
        ('ADJUSTMENT', 'Adjustment'),
        ('EXPIRED', 'Expired'),
        ('RETURNED', 'Returned'),
    ]
    
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=15, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.IntegerField()
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_movements')
    notes = models.TextField(blank=True)
    date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.medicine.name} ({self.quantity})"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.movement_type in ['PURCHASE', 'RETURNED']:
            self.medicine.stock_quantity += self.quantity
        elif self.movement_type in ['DISPENSE', 'EXPIRED', 'ADJUSTMENT']:
            self.medicine.stock_quantity -= self.quantity
        self.medicine.save(update_fields=['stock_quantity', 'updated_at'])


class LabTestType(models.Model):
    """Dynamic lab test types that can be added by admin"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @classmethod
    def get_choices(cls):
        """Get test types as choices for form"""
        return [(t.code, t.name) for t in cls.objects.filter(is_active=True)]


class LabRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='lab_requests')
    test_type = models.ForeignKey(LabTestType, on_delete=models.CASCADE, related_name='lab_requests', null=True, blank=True)
    test_name = models.CharField(max_length=50, choices=[], blank=True)  # Legacy field - kept for backward compatibility
    custom_test_name = models.CharField(max_length=200, blank=True, help_text="For custom test types")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_lab_tests')
    technician = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_lab_tests')
    result = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    date = models.DateTimeField(default=timezone.now)
    completed_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        if self.test_type:
            return f"{self.test_type.name} - Visit #{self.visit_id}"
        return f"{self.get_test_name_display()} - Visit #{self.visit_id}"
    
    def get_test_name_display(self):
        if self.test_type:
            return self.test_type.name
        return self.custom_test_name or self.test_name


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('LOW_STOCK', 'Low Stock'),
        ('EXPIRED_MEDICINE', 'Expired Medicine'),
        ('NEW_VISIT', 'New Visit'),
        ('LAB_RESULT', 'Lab Result Ready'),
        ('SYSTEM', 'System'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    is_read = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()}: {self.title}"


class DailyReport(models.Model):
    report_date = models.DateField(unique=True)
    total_patients = models.PositiveIntegerField(default=0)
    students_count = models.PositiveIntegerField(default=0)
    staff_count = models.PositiveIntegerField(default=0)
    completed_visits = models.PositiveIntegerField(default=0)
    lab_tests_conducted = models.PositiveIntegerField(default=0)
    medicines_dispensed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-report_date']
    
    def __str__(self):
        return f"Report for {self.report_date}"


class Report(models.Model):
    REPORT_TYPE_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
    ]
    
    REPORT_FOR_CHOICES = [
        ('OVERALL', 'Overall Clinic'),
        ('NURSE', 'Nursing'),
        ('DOCTOR', 'Doctor/Consultation'),
        ('LAB', 'Laboratory'),
        ('PHARMACY', 'Pharmacy'),
    ]
    
    title = models.CharField(max_length=200)
    report_type = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES)
    report_for = models.CharField(max_length=20, choices=REPORT_FOR_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Report Data (stored as JSON)
    data = models.JSONField(default=dict)
    
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.get_report_for_display()} ({self.start_date} to {self.end_date})"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
        ('LOGIN', 'Logged In'),
        ('LOGOUT', 'Logged Out'),
        ('VIEW', 'Viewed'),
        ('DISPENSE', 'Dispensed Medicine'),
        ('PRESCRIBE', 'Prescribed'),
        ('REGISTER', 'Registered'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Audit Logs'
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"
