from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from clinic.models import Patient, Medicine
from datetime import date, timedelta

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates sample data for the clinic'

    def handle(self, *args, **options):
        self.stdout.write('Creating users...')
        
        if not User.objects.filter(username='admin').exists():
            admin = User.objects.create_superuser(
                username='admin',
                email='admin@kumi.ac.ug',
                password='admin123',
                first_name='System',
                last_name='Administrator',
                role='ADMIN'
            )
            self.stdout.write(f'Created admin user: {admin.username}')
        
        roles = ['RECEPTIONIST', 'NURSE', 'DOCTOR', 'LAB_TECHNICIAN', 'PHARMACIST']
        role_names = ['Receptionist', 'Nurse', 'Doctor', 'Lab Technician', 'Pharmacist']
        
        for i, role in enumerate(roles):
            username = role.lower()
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    email=f'{username}@kumi.ac.ug',
                    password=f'{username}123',
                    first_name=role_names[i],
                    last_name='Staff',
                    role=role
                )
                self.stdout.write(f'Created user: {user.username} (role: {role})')
        
        self.stdout.write('Creating patients...')
        
        patients_data = [
            {'name': 'John Okello', 'type': 'STUDENT', 'id': '23/SS/03/003/BSCIT/FT', 'dept': 'Computer Science', 'gender': 'MALE'},
            {'name': 'Sarah Amoit', 'type': 'STUDENT', 'id': 'STU/2024/002', 'dept': 'Business Administration', 'gender': 'FEMALE'},
            {'name': 'Dr. Michael Otieno', 'type': 'STAFF', 'id': 'STF/2023/015', 'dept': 'Faculty of Medicine', 'gender': 'MALE'},
            {'name': 'Grace Nakato', 'type': 'STUDENT', 'id': 'STU/2024/003', 'dept': 'Nursing', 'gender': 'FEMALE'},
            {'name': 'Robert Kigen', 'type': 'STAFF', 'id': 'STF/2022/008', 'dept': 'Finance', 'gender': 'MALE'},
        ]
        
        for p in patients_data:
            if not Patient.objects.filter(university_id=p['id']).exists():
                patient = Patient.objects.create(
                    full_name=p['name'],
                    patient_type=p['type'],
                    university_id=p['id'],
                    department=p['dept'],
                    phone=f'+2567{p["id"][-6:]}',
                    gender=p['gender'],
                    date_of_birth=date(2000, 1, 15)
                )
                self.stdout.write(f'Created patient: {patient.full_name}')
        
        self.stdout.write('Creating medicines...')
        
        medicines_data = [
            {'name': 'Paracetamol 500mg', 'category': 'TABLET', 'stock': 500, 'unit': 'tablets', 'min': 50},
            {'name': 'Amoxicillin 250mg', 'category': 'CAPSULE', 'stock': 200, 'unit': 'capsules', 'min': 30},
            {'name': 'ORS Solution', 'category': 'SYRUP', 'stock': 50, 'unit': 'sachets', 'min': 20},
            {'name': 'Ibuprofen 400mg', 'category': 'TABLET', 'stock': 300, 'unit': 'tablets', 'min': 40},
            {'name': 'Cough Syrup', 'category': 'SYRUP', 'stock': 30, 'unit': 'bottles', 'min': 15},
            {'name': 'Metronidazole 200mg', 'category': 'TABLET', 'stock': 150, 'unit': 'tablets', 'min': 25},
            {'name': 'Antimalarial', 'category': 'TABLET', 'stock': 100, 'unit': 'tablets', 'min': 20},
            {'name': 'Hydrogen Peroxide', 'category': 'OTHER', 'stock': 20, 'unit': 'bottles', 'min': 5},
        ]
        
        for m in medicines_data:
            if not Medicine.objects.filter(name=m['name']).exists():
                medicine = Medicine.objects.create(
                    name=m['name'],
                    category=m['category'],
                    stock_quantity=m['stock'],
                    unit=m['unit'],
                    expiry_date=date.today() + timedelta(days=365),
                    minimum_stock_level=m['min']
                )
                self.stdout.write(f'Created medicine: {medicine.name}')
        
        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))
        self.stdout.write('')
        self.stdout.write('Login credentials:')
        self.stdout.write('  Admin: admin / admin123')
        self.stdout.write('  Receptionist: receptionist / receptionist123')
        self.stdout.write('  Nurse: nurse / nurse123')
        self.stdout.write('  Doctor: doctor / doctor123')
        self.stdout.write('  Lab Technician: lab_technician / lab_technician123')
        self.stdout.write('  Pharmacist: pharmacist / pharmacist123')
