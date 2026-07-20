from celery import shared_task

from apps.accounts.certificates import scan_expiring_certificates


@shared_task(name="accounts.scan_expiring_certificates")
def scan_expiring_certificates_task(alert_days: int = 30) -> int:
    return scan_expiring_certificates(alert_days=alert_days)
