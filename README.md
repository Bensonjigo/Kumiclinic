# Kumi University Clinic Management System

A production-ready Django-based clinic management system for Kumi University.

## Features

- **Patient Management**: Register and manage students and staff as patients
- **Visit Workflow**: Track patient visits from registration to completion
- **Triage**: Nurses record patient vitals (temperature, blood pressure, weight, etc.)
- **Consultation**: Doctors diagnose and create treatment plans
- **Prescriptions**: Doctors prescribe medicines, pharmacists dispense
- **Lab Tests**: Request and record lab test results
- **Counselling**: Refer patients for mental health support, stress management, and other counselling services
- **Scanning**: Refer patients for X-ray, ultrasound, CT, MRI, and other imaging services
- **Medicine Inventory**: Track stock levels with low-stock alerts
- **Reports**: Daily statistics and reports
- **Role-Based Access**: Different permissions for Nurse, Doctor, Lab Technician, Pharmacist, Counsellor, Scan Technician, Store Manager, Admin
- **REST API**: Full Django REST Framework API
- **Dashboard UI**: Clean web interface with Tailwind CSS

## Quick Start

1. Navigate to the project directory:
   ```bash
   cd kumiclinic
   ```

2. Run migrations:
   ```bash
   python manage.py migrate
   ```

3. Create sample data:
   ```bash
   python manage.py setup_sample_data
   ```

4. Run the development server:
   ```bash
   python manage.py runserver
   ```

5. Access the application at http://127.0.0.1:8000

## Login Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Nurse | nurse | nurse123 |
| Doctor | doctor | doctor123 |
| Lab Technician | lab_technician | lab_technician123 |
| Pharmacist | pharmacist | pharmacist123 |
| Counsellor | counsellor | counsellor123 |
| Scan Technician | scan_tech | scan_tech123 |

## User Roles

| Role | Description |
|------|-------------|
| **Admin** | Full system access, manage settings, inventory, lab tests, counselling & scan types |
| **Nurse** | Patient registration, triage, view history |
| **Doctor** | Consultations, prescriptions, lab/counselling/scanning referrals |
| **Lab Technician** | Process and record lab test results |
| **Pharmacist** | Dispense prescribed medicines |
| **Counsellor** | Handle patient referrals for mental health/counselling services |
| **Scan Technician** | Handle patient referrals for imaging services |
| **Store Manager** | Manage medicine inventory |

## Complete Patient Workflow

### Standard Visit
1. **Reception/Nurse**: Register patient → Create visit
2. **Nurse**: Record triage vitals → Status: WAITING_FOR_DOCTOR
3. **Doctor**: Add diagnosis and prescriptions
4. **Pharmacist**: Dispense medicine → Status: COMPLETED

### With Lab Tests
1. **Reception/Nurse**: Register patient → Create visit
2. **Nurse**: Record triage vitals → Status: WAITING_FOR_DOCTOR
3. **Doctor**: Order lab tests → Status: IN_LAB
4. **Lab Technician**: Record results → Status: WAITING_FOR_DOCTOR
5. **Doctor**: Review results, add prescriptions
6. **Pharmacist**: Dispense medicine → Status: COMPLETED

### With Counselling Referral
1. **Reception/Nurse**: Register patient → Create visit
2. **Nurse**: Record triage vitals → Status: WAITING_FOR_DOCTOR
3. **Doctor**: Refer to counselling → Status: IN_COUNSELLING
4. **Counsellor**: Complete session → Status: WAITING_FOR_DOCTOR
5. **Doctor**: Final consultation and prescriptions
6. **Pharmacist**: Dispense medicine → Status: COMPLETED

### With Scanning Referral
1. **Reception/Nurse**: Register patient → Create visit
2. **Nurse**: Record triage vitals → Status: WAITING_FOR_DOCTOR
3. **Doctor**: Refer for scanning → Status: IN_SCANNING
4. **Scan Technician**: Complete scan, record findings → Status: WAITING_FOR_DOCTOR
5. **Doctor**: Review findings, add prescriptions
6. **Pharmacist**: Dispense medicine → Status: COMPLETED

## API Endpoints

- `POST /api/login/` - Get authentication token
- `GET /api/patients/` - List patients
- `POST /api/patients/` - Register patient
- `GET /api/visits/` - List visits
- `POST /api/visits/` - Create new visit
- `GET /api/triages/` - List triages
- `GET /api/medicines/` - List medicines
- `GET /api/stock-movements/` - Stock history

## Visit Status Flow

```
REGISTERED → WAITING_FOR_TRIAGE → WAITING_FOR_DOCTOR
                                              ↓
                        ┌─────────────────────┼─────────────────────┐
                        ↓                     ↓                     ↓
                     IN_LAB           IN_COUNSELLING          IN_SCANNING
                        ↓                     ↓                     ↓
                        └─────────────────────┼─────────────────────┘
                                              ↓
                                    WAITING_FOR_DOCTOR
                                              ↓
                                    WAITING_FOR_PHARMACY
                                              ↓
                                          COMPLETED
```

## Tech Stack

- Django 6.x
- Django REST Framework
- Tailwind CSS
- HTMX
- SQLite (default, easily switchable to PostgreSQL)

## Project Structure

```
kumiclinic/
├── clinic/                 # Main app
│   ├── models.py          # Database models
│   ├── template_views.py  # Web views
│   ├── views.py           # API views
│   └── urls.py            # URL routing
├── templates/             # HTML templates
│   ├── base.html         # Base template with navigation
│   ├── dashboard/        # Role-specific dashboards
│   └── clinic/           # General clinic templates
├── static/               # CSS, JS, images
├── media/                # Uploaded files
└── settings.py           # Django settings
```
