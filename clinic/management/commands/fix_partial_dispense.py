from django.core.management.base import BaseCommand
from clinic.models import Prescription
from django.utils import timezone

class Command(BaseCommand):
    help = 'Fix prescriptions that were partially dispensed but no remaining prescription was created'

    def handle(self, *args, **options):
        # Find prescriptions that were partially dispensed (quantity < original)
        # These are prescriptions where is_dispensed=True but notes don't mention "REMAINING"
        
        # Get all dispensed prescriptions
        dispensed = Prescription.objects.filter(is_dispensed=True)
        
        fixed_count = 0
        
        for rx in dispensed:
            # Check if this has notes about original quantity
            if rx.notes and 'Original qty:' in rx.notes:
                # This was already processed, skip
                continue
            
            # This might be a partial dispense that wasn't properly handled
            # We can't know the original quantity, so we can't fix it automatically
            # Just log it
            self.stdout.write(f'Prescription {rx.id}: {rx.medicine.name} - qty={rx.quantity} - already dispensed')
        
        self.stdout.write(self.style.SUCCESS('Done!'))
        self.stdout.write('Note: Cannot automatically fix old partial dispenses without original quantity info.')
        self.stdout.write('Recommend: Manually review and create remaining prescriptions if needed.')
