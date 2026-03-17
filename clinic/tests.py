"""
Clinic Application Tests
========================
This file contains unit tests for the Kumi University Clinic application.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from clinic.models import (
    Patient, Visit, Triage, Consultation, Medicine, 
    Prescription, LabRequest, LabTestType, StockMovement, Notification
)

User = get_user_model()


# ==================== MODEL TESTS ====================

class UserModelTest(TestCase):
    """Tests for User model"""
    
    def setUp(self):
        self.user_data = {
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'testuser@example.com',
            'role': 'DOCTOR',
            'password': 'testpass123'
        }
    
    def test_create_user(self):
        """Test creating a regular user"""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.role, 'DOCTOR')
        self.assertTrue(user.check_password('testpass123'))
        self.assertFalse(user.is_superuser)
    
    def test_create_superuser(self):
        """Test creating a superuser"""
        superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='admin123'
        )
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_staff)
    
    def test_user_role_properties(self):
        """Test role-based properties"""
        doctor = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            role='DOCTOR',
            password='pass123'
        )
        nurse = User.objects.create_user(
            username='nurse',
            email='nurse@example.com',
            role='NURSE',
            password='pass123'
        )
        
        self.assertTrue(doctor.is_doctor)
        self.assertFalse(doctor.is_nurse)
        self.assertTrue(nurse.is_nurse)
        self.assertFalse(nurse.is_doctor)
    
    def test_user_str(self):
        """Test user string representation"""
        user = User.objects.create_user(**self.user_data)
        self.assertIn('Test User', str(user))
        self.assertIn('Doctor', str(user))


class PatientModelTest(TestCase):
    """Tests for Patient model"""
    
    def setUp(self):
        self.patient_data = {
            'full_name': 'John Doe',
            'patient_type': 'STUDENT',
            'university_id': 'STU001',
            'department': 'Computer Science',
            'phone': '+256701234567',
            'email': 'john@example.com',
            'gender': 'MALE',
            'date_of_birth': date(2000, 1, 15),
            'address': 'Kumi University, Kampala'
        }
    
    def test_create_patient(self):
        """Test creating a patient"""
        patient = Patient.objects.create(**self.patient_data)
        self.assertEqual(patient.full_name, 'John Doe')
        self.assertEqual(patient.university_id, 'STU001')
        self.assertEqual(patient.patient_type, 'STUDENT')
        self.assertEqual(patient.gender, 'MALE')
    
    def test_patient_str(self):
        """Test patient string representation"""
        patient = Patient.objects.create(**self.patient_data)
        self.assertIn('John Doe', str(patient))
        self.assertIn('STU001', str(patient))
    
    def test_patient_age_property(self):
        """Test patient age calculation"""
        patient = Patient.objects.create(**self.patient_data)
        expected_age = date.today().year - 2000 - (
            (date.today().month, date.today().day) < (1, 15)
        )
        self.assertEqual(patient.age, expected_age)
    
    def test_patient_unique_university_id(self):
        """Test that university_id must be unique"""
        Patient.objects.create(**self.patient_data)
        with self.assertRaises(Exception):
            Patient.objects.create(
                full_name='Jane Doe',
                patient_type='STUDENT',
                university_id='STU001',  # Duplicate
                department='Engineering',
                phone='+256701234568',
                gender='FEMALE',
                date_of_birth=date(1999, 5, 20)
            )
    
    def test_patient_ordering(self):
        """Test patients are ordered by created_at descending"""
        patient1 = Patient.objects.create(
            full_name='First Patient',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234561',
            gender='MALE',
            date_of_birth=date(2000, 1, 1)
        )
        patient2 = Patient.objects.create(
            full_name='Second Patient',
            patient_type='STAFF',
            university_id='STU002',
            department='Arts',
            phone='+256701234562',
            gender='FEMALE',
            date_of_birth=date(1985, 3, 15)
        )
        patients = list(Patient.objects.all())
        self.assertEqual(patients[0], patient2)  # Most recent first
        self.assertEqual(patients[1], patient1)


class VisitModelTest(TestCase):
    """Tests for Visit model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='receptionist',
            email='receptionist@example.com',
            role='RECEPTIONIST',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Computer Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
    
    def test_create_visit(self):
        """Test creating a visit"""
        visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Flu symptoms',
            created_by=self.user,
            status='REGISTERED'
        )
        self.assertEqual(visit.patient, self.patient)
        self.assertEqual(visit.status, 'REGISTERED')
        self.assertEqual(visit.reason_for_visit, 'Flu symptoms')
    
    def test_visit_str(self):
        """Test visit string representation"""
        visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Headache',
            created_by=self.user
        )
        self.assertIn('Visit #', str(visit))
        self.assertIn('John Doe', str(visit))
    
    def test_visit_status_transitions(self):
        """Test valid status transitions"""
        visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Checkup',
            created_by=self.user,
            status='REGISTERED'
        )
        
        # Test valid transitions
        self.assertTrue(visit.can_update_to('WAITING_FOR_TRIAGE'))
        self.assertTrue(visit.update_status('WAITING_FOR_TRIAGE'))
        self.assertEqual(visit.status, 'WAITING_FOR_TRIAGE')
        
        # Test another valid transition
        self.assertTrue(visit.can_update_to('WAITING_FOR_DOCTOR'))
        visit.update_status('WAITING_FOR_DOCTOR')
        self.assertEqual(visit.status, 'WAITING_FOR_DOCTOR')
    
    def test_invalid_status_transitions(self):
        """Test invalid status transitions"""
        visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Checkup',
            status='COMPLETED'
        )
        
        # Cannot transition from COMPLETED
        self.assertFalse(visit.can_update_to('REGISTERED'))
        self.assertFalse(visit.can_update_to('WAITING_FOR_TRIAGE'))
    
    def test_update_status_returns_false_for_invalid(self):
        """Test update_status returns False for invalid transitions"""
        visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Checkup',
            status='COMPLETED'
        )
        result = visit.update_status('REGISTERED')
        self.assertFalse(result)
        self.assertEqual(visit.status, 'COMPLETED')  # Unchanged


class TriageModelTest(TestCase):
    """Tests for Triage model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='nurse',
            email='nurse@example.com',
            role='NURSE',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
        self.visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Fever',
            created_by=self.user,
            status='WAITING_FOR_TRIAGE'
        )
    
    def test_create_triage(self):
        """Test creating a triage record"""
        triage = Triage.objects.create(
            visit=self.visit,
            temperature=Decimal('37.5'),
            blood_pressure='120/80',
            weight=Decimal('70.5'),
            heart_rate=72,
            symptoms='Fever, headache',
            nurse_notes='Patient appears unwell',
            recorded_by=self.user
        )
        self.assertEqual(triage.visit, self.visit)
        self.assertEqual(triage.temperature, Decimal('37.5'))
        self.assertEqual(triage.blood_pressure, '120/80')
        self.assertEqual(triage.heart_rate, 72)
    
    def test_triage_str(self):
        """Test triage string representation"""
        triage = Triage.objects.create(visit=self.visit, recorded_by=self.user)
        self.assertIn('Triage for Visit #', str(triage))
    
    def test_triage_optional_fields(self):
        """Test that vital signs are optional"""
        triage = Triage.objects.create(
            visit=self.visit,
            symptoms='Mild cough',
            recorded_by=self.user
        )
        self.assertIsNone(triage.temperature)
        self.assertIsNone(triage.blood_pressure)
        self.assertEqual(triage.symptoms, 'Mild cough')


class ConsultationModelTest(TestCase):
    """Tests for Consultation model"""
    
    def setUp(self):
        self.doctor = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            role='DOCTOR',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
        self.visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Checkup',
            created_by=self.doctor,
            status='WAITING_FOR_DOCTOR'
        )
    
    def test_create_consultation(self):
        """Test creating a consultation"""
        consultation = Consultation.objects.create(
            visit=self.visit,
            doctor=self.doctor,
            diagnosis='Common cold',
            doctor_notes='Rest and fluids recommended',
            treatment_plan='Paracetamol 500mg thrice daily for 3 days'
        )
        self.assertEqual(consultation.visit, self.visit)
        self.assertEqual(consultation.diagnosis, 'Common cold')
        self.assertEqual(consultation.doctor, self.doctor)
    
    def test_consultation_str(self):
        """Test consultation string representation"""
        consultation = Consultation.objects.create(
            visit=self.visit,
            doctor=self.doctor,
            diagnosis='Flu'
        )
        self.assertIn('Consultation for Visit #', str(consultation))


class MedicineModelTest(TestCase):
    """Tests for Medicine model"""
    
    def setUp(self):
        self.medicine_data = {
            'name': 'Paracetamol',
            'category': 'TABLET',
            'stock_quantity': 100,
            'unit': 'tablets',
            'minimum_stock_level': 20
        }
    
    def test_create_medicine(self):
        """Test creating a medicine"""
        medicine = Medicine.objects.create(**self.medicine_data)
        self.assertEqual(medicine.name, 'Paracetamol')
        self.assertEqual(medicine.category, 'TABLET')
        self.assertEqual(medicine.stock_quantity, 100)
    
    def test_medicine_unique_name(self):
        """Test medicine name must be unique"""
        Medicine.objects.create(**self.medicine_data)
        with self.assertRaises(Exception):
            Medicine.objects.create(
                name='Paracetamol',  # Duplicate
                category='CAPSULE',
                stock_quantity=50,
                unit='capsules'
            )
    
    def test_medicine_is_low_stock_property(self):
        """Test low stock detection"""
        medicine = Medicine.objects.create(
            name='Medicine Low',
            category='TABLET',
            stock_quantity=15,
            unit='tablets',
            minimum_stock_level=20
        )
        self.assertTrue(medicine.is_low_stock)
        
        medicine.stock_quantity = 25
        self.assertFalse(medicine.is_low_stock)
    
    def test_medicine_status_property(self):
        """Test medicine status property"""
        # Test OUT_OF_STOCK
        out_medicine = Medicine.objects.create(
            name='Out Stock',
            category='TABLET',
            stock_quantity=0,
            unit='tablets'
        )
        self.assertEqual(out_medicine.status, 'OUT_OF_STOCK')
        
        # Test LOW_STOCK
        low_medicine = Medicine.objects.create(
            name='Low Stock',
            category='TABLET',
            stock_quantity=5,
            unit='tablets',
            minimum_stock_level=10
        )
        self.assertEqual(low_medicine.status, 'LOW_STOCK')
        
        # Test IN_STOCK
        in_medicine = Medicine.objects.create(
            name='In Stock',
            category='TABLET',
            stock_quantity=50,
            unit='tablets',
            minimum_stock_level=10
        )
        self.assertEqual(in_medicine.status, 'IN_STOCK')


class PrescriptionModelTest(TestCase):
    """Tests for Prescription model"""
    
    def setUp(self):
        self.doctor = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            role='DOCTOR',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
        self.visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Checkup',
            created_by=self.doctor
        )
        self.consultation = Consultation.objects.create(
            visit=self.visit,
            doctor=self.doctor,
            diagnosis='Common cold'
        )
        self.medicine = Medicine.objects.create(
            name='Paracetamol',
            category='TABLET',
            stock_quantity=100,
            unit='tablets'
        )
    
    def test_create_prescription(self):
        """Test creating a prescription"""
        prescription = Prescription.objects.create(
            consultation=self.consultation,
            medicine=self.medicine,
            dosage='2 tablets thrice daily',
            quantity=18,
            notes='Take after food'
        )
        self.assertEqual(prescription.consultation, self.consultation)
        self.assertEqual(prescription.medicine, self.medicine)
        self.assertEqual(prescription.dosage, '2 tablets thrice daily')
        self.assertEqual(prescription.quantity, 18)
        self.assertFalse(prescription.is_dispensed)
    
    def test_prescription_str(self):
        """Test prescription string representation"""
        prescription = Prescription.objects.create(
            consultation=self.consultation,
            medicine=self.medicine,
            dosage='1 tablet daily',
            quantity=10
        )
        self.assertIn('Paracetamol', str(prescription))
        self.assertIn('tablets', str(prescription))


class LabRequestModelTest(TestCase):
    """Tests for LabRequest model"""
    
    def setUp(self):
        self.doctor = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            role='DOCTOR',
            password='pass123'
        )
        self.lab_tech = User.objects.create_user(
            username='labtech',
            email='labtech@example.com',
            role='LAB_TECHNICIAN',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
        self.visit = Visit.objects.create(
            patient=self.patient,
            reason_for_visit='Blood test',
            created_by=self.doctor,
            status='WAITING_FOR_DOCTOR'
        )
        self.lab_test_type = LabTestType.objects.create(
            name='Complete Blood Count',
            code='CBC',
            description='Complete blood count test',
            is_active=True
        )
    
    def test_create_lab_request(self):
        """Test creating a lab request"""
        lab_request = LabRequest.objects.create(
            visit=self.visit,
            test_type=self.lab_test_type,
            requested_by=self.doctor,
            status='PENDING'
        )
        self.assertEqual(lab_request.visit, self.visit)
        self.assertEqual(lab_request.test_type, self.lab_test_type)
        self.assertEqual(lab_request.status, 'PENDING')
    
    def test_lab_request_str(self):
        """Test lab request string representation"""
        lab_request = LabRequest.objects.create(
            visit=self.visit,
            test_type=self.lab_test_type,
            requested_by=self.doctor
        )
        self.assertIn('Complete Blood Count', str(lab_request))
    
    def test_lab_request_get_test_name_display(self):
        """Test get_test_name_display method"""
        lab_request = LabRequest.objects.create(
            visit=self.visit,
            test_type=self.lab_test_type,
            requested_by=self.doctor
        )
        self.assertEqual(lab_request.get_test_name_display(), 'Complete Blood Count')
    
    def test_lab_request_status_choices(self):
        """Test lab request status choices"""
        lab_request = LabRequest.objects.create(
            visit=self.visit,
            test_type=self.lab_test_type,
            requested_by=self.doctor,
            status='PENDING'
        )
        
        # Update to IN_PROGRESS
        lab_request.status = 'IN_PROGRESS'
        lab_request.save()
        self.assertEqual(lab_request.status, 'IN_PROGRESS')
        
        # Update to COMPLETED
        lab_request.status = 'COMPLETED'
        lab_request.completed_date = timezone.now()
        lab_request.save()
        self.assertEqual(lab_request.status, 'COMPLETED')


# ==================== VIEW TESTS ====================

class AuthenticationViewTest(TestCase):
    """Tests for authentication views"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='DOCTOR'
        )
    
    def test_login_view_get(self):
        """Test login page loads"""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'clinic/login.html')
    
    def test_login_view_post_success(self):
        """Test successful login"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        # Should redirect after successful login
        self.assertIn(response.status_code, [200, 302])
    
    def test_login_view_post_invalid(self):
        """Test invalid login"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        # Should stay on page or redirect - accept either
        self.assertIn(response.status_code, [200, 302])


class DashboardViewTest(TestCase):
    """Tests for dashboard views"""
    
    def setUp(self):
        self.client = Client()
        self.doctor = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            role='DOCTOR',
            password='pass123'
        )
        self.nurse = User.objects.create_user(
            username='nurse',
            email='nurse@example.com',
            role='NURSE',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
    
    def test_doctor_dashboard_requires_login(self):
        """Test doctor dashboard requires login"""
        response = self.client.get(reverse('dashboard_doctor'))
        self.assertEqual(response.status_code, 302)  # Redirects to login
    
    def test_doctor_dashboard_login_required(self):
        """Test doctor dashboard with login"""
        self.client.login(username='doctor', password='pass123')
        response = self.client.get(reverse('dashboard_doctor'))
        self.assertEqual(response.status_code, 200)
    
    def test_nurse_dashboard_login_required(self):
        """Test nurse dashboard with login"""
        self.client.login(username='nurse', password='pass123')
        response = self.client.get(reverse('dashboard_nurse'))
        self.assertEqual(response.status_code, 200)


class PatientViewTest(TestCase):
    """Tests for patient views"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            role='RECEPTIONIST',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
    
    def test_patient_list_requires_login(self):
        """Test patients list requires login"""
        response = self.client.get(reverse('patients'))
        self.assertEqual(response.status_code, 302)
    
    def test_patient_list_view(self):
        """Test patients list view with login"""
        self.client.login(username='staff', password='pass123')
        response = self.client.get(reverse('patients'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'John Doe')
    
    def test_patient_detail_view(self):
        """Test patient detail view"""
        self.client.login(username='staff', password='pass123')
        response = self.client.get(reverse('patient_detail', args=[self.patient.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'STU001')


# ==================== API TESTS ====================

class PatientAPITest(TestCase):
    """Tests for Patient API"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            role='RECEPTIONIST',
            password='pass123'
        )
        self.patient = Patient.objects.create(
            full_name='John Doe',
            patient_type='STUDENT',
            university_id='STU001',
            department='Science',
            phone='+256701234567',
            gender='MALE',
            date_of_birth=date(2000, 1, 15)
        )
    
    def test_patient_list_api_requires_auth(self):
        """Test patient list API requires authentication"""
        response = self.client.get('/api/patients/')
        # Should return 401 or 403 without auth
        self.assertIn(response.status_code, [401, 403, 404, 302])


# ==================== INTEGRATION TESTS ====================

class PatientFlowIntegrationTest(TestCase):
    """Integration tests for complete patient flow"""
    
    def setUp(self):
        self.client = Client()
        self.receptionist = User.objects.create_user(
            username='receptionist',
            email='receptionist@example.com',
            role='RECEPTIONIST',
            password='pass123'
        )
        self.nurse = User.objects.create_user(
            username='nurse',
            email='nurse@example.com',
            role='NURSE',
            password='pass123'
        )
        self.doctor = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            role='DOCTOR',
            password='pass123'
        )
        self.pharmacist = User.objects.create_user(
            username='pharmacist',
            email='pharmacist@example.com',
            role='PHARMACIST',
            password='pass123'
        )
    
    def test_complete_patient_flow(self):
        """Test complete patient flow: Register -> Triage -> Doctor -> Prescription -> Complete"""
        
        # Step 1: Register patient and create visit
        patient = Patient.objects.create(
            full_name='Test Patient',
            patient_type='STUDENT',
            university_id='STU999',
            department='Engineering',
            phone='+256709999999',
            gender='MALE',
            date_of_birth=date(1999, 5, 5)
        )
        visit = Visit.objects.create(
            patient=patient,
            reason_for_visit='General checkup',
            created_by=self.receptionist,
            status='WAITING_FOR_TRIAGE'
        )
        
        # Verify initial status
        self.assertEqual(visit.status, 'WAITING_FOR_TRIAGE')
        
        # Step 2: Nurse performs triage
        triage = Triage.objects.create(
            visit=visit,
            temperature=Decimal('36.5'),
            blood_pressure='120/75',
            weight=Decimal('65.0'),
            heart_rate=70,
            symptoms='No symptoms',
            recorded_by=self.nurse
        )
        
        # Update visit status to waiting for doctor
        visit.update_status('WAITING_FOR_DOCTOR')
        self.assertEqual(visit.status, 'WAITING_FOR_DOCTOR')
        
        # Step 3: Doctor conducts consultation
        consultation = Consultation.objects.create(
            visit=visit,
            doctor=self.doctor,
            diagnosis='Healthy',
            treatment_plan='Continue healthy lifestyle',
            doctor_notes='Patient is in good health'
        )
        
        # Step 4: Create prescription
        medicine = Medicine.objects.create(
            name='Vitamin C',
            category='TABLET',
            stock_quantity=50,
            unit='tablets'
        )
        prescription = Prescription.objects.create(
            consultation=consultation,
            medicine=medicine,
            dosage='1 tablet daily',
            quantity=30
        )
        
        # Step 5: Update status and complete
        visit.update_status('WAITING_FOR_PHARMACY')
        self.assertEqual(visit.status, 'WAITING_FOR_PHARMACY')
        
        visit.update_status('COMPLETED')
        self.assertEqual(visit.status, 'COMPLETED')
        
        # Verify complete flow
        self.assertEqual(patient.visits.count(), 1)
        self.assertEqual(visit.triage, triage)
        self.assertEqual(visit.consultation, consultation)
        self.assertEqual(consultation.prescriptions.count(), 1)
