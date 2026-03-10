# Kumi University Clinic Management System

A production-ready Django-based clinic management system for Kumi University.

## Features

- **Patient Management**: Register and manage students and staff as patients
- **Visit Workflow**: Track patient visits from registration to completion
- **Triage**: Nurses record patient vitals (temperature, blood pressure, weight, etc.)
- **Consultation**: Doctors diagnose and create treatment plans
- **Prescriptions**: Doctors prescribe medicines, pharmacists dispense
- **Lab Tests**: Request and record lab test results
- **Medicine Inventory**: Track stock levels with low-stock alerts
- **Reports**: Daily statistics and reports
- **Role-Based Access**: Different permissions for Receptionist, Nurse, Doctor, Lab Technician, Pharmacist, Admin
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
| Receptionist | receptionist | receptionist123 |
| Nurse | nurse | nurse123 |
| Doctor | doctor | doctor123 |
| Lab Technician | lab_technician | lab_technician123 |
| Pharmacist | pharmacist | pharmacist123 |

## API Endpoints

- `POST /api/login/` - Get authentication token
- `GET /api/patients/` - List patients
- `POST /api/patients/` - Register patient
- `GET /api/visits/` - List visits
- `POST /api/visits/` - Create new visit
- `GET /api/triages/` - List triages
- `GET /api/medicines/` - List medicines
- `GET /api/stock-movements/` - Stock history

## Workflow Example

1. **Reception**: Register patient → Create visit (status: WAITING_FOR_TRIAGE)
2. **Nurse**: Record triage vitals → Status changes to WAITING_FOR_DOCTOR
3. **Doctor**: Add diagnosis, prescribe medicine/lab test → Status changes to WAITING_FOR_PHARMACY or IN_LAB
4. **Lab Tech**: Record lab results → Status changes to WAITING_FOR_DOCTOR
5. **Pharmacist**: Dispense medicine → Status changes to COMPLETED

## Tech Stack

- Django 6.x
- Django REST Framework
- Tailwind CSS
- HTMX
- SQLite (default, easily switchable to PostgreSQL)
