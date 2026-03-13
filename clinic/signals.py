from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import (
    Prescription, Medicine, StockMovement, Visit, LabRequest, Notification
)

User = get_user_model()


@receiver(pre_save, sender=Prescription)
def prescription_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Prescription.objects.get(pk=instance.pk)
            instance._was_dispensed = old_instance.is_dispensed
        except Prescription.DoesNotExist:
            instance._was_dispensed = False
    else:
        instance._was_dispensed = False


@receiver(post_save, sender=Prescription)
def prescription_post_save(sender, instance, created, **kwargs):
    if instance.is_dispensed and not getattr(instance, '_was_dispensed', False):
        StockMovement.objects.create(
            medicine=instance.medicine,
            movement_type='DISPENSE',
            quantity=instance.quantity,
            performed_by=None,
            notes=f"Auto-dispensed for Visit #{instance.consultation.visit_id}"
        )


@receiver(pre_save, sender=Medicine)
def medicine_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Medicine.objects.get(pk=instance.pk)
            instance._old_stock = old_instance.stock_quantity
        except Medicine.DoesNotExist:
            instance._old_stock = 0
    else:
        instance._old_stock = 0


@receiver(post_save, sender=Medicine)
def medicine_post_save(sender, instance, created, **kwargs):
    if instance.stock_quantity < instance.minimum_stock_level and instance._old_stock >= instance.minimum_stock_level:
        Notification.objects.create(
            title=f"Low Stock Alert: {instance.name}",
            message=f"{instance.name} is running low. Current stock: {instance.stock_quantity} {instance.unit}",
            notification_type='LOW_STOCK',
            user_id=1
        )


@receiver(post_save, sender=Visit)
def visit_post_save(sender, instance, created, **kwargs):
    if created:
        admins = User.objects.filter(role='ADMIN')
        for admin in admins:
            Notification.objects.create(
                title=f"New Patient Visit",
                message=f"{instance.patient.full_name} has been registered. Reason: {instance.reason_for_visit}",
                notification_type='NEW_VISIT',
                user=admin
            )


@receiver(post_save, sender=LabRequest)
def lab_request_post_save(sender, instance, created, **kwargs):
    if instance.status == 'COMPLETED' and instance.requested_by:
        Notification.objects.create(
            title=f"Lab Result Ready",
            message=f"Your lab test ({instance.get_test_name_display()}) results are ready.",
            notification_type='LAB_RESULT',
            user=instance.requested_by
        )
