from django.db import models

class Account(models.Model):
    name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20, unique=True)
    password = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    # Changed to FloatField to prevent the Decimal128 save error
    balance = models.FloatField(default=0.0) 
    is_frozen = models.BooleanField(default=False) 
    failed_login_attempts = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if self.balance is not None:
            self.balance = float(str(self.balance))
        super().save(*args, **kwargs)
        
        if is_new and self.email:
            try:
                from django.core.mail import send_mail
                from django.conf import settings
                subject = "Welcome to Django Bank Project"
                message = f"Dear {self.name},\n\nYour account has been successfully created.\nAccount Number: {self.account_number}\n\nWe are delighted to have you on board!"
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [self.email],
                    fail_silently=True,
                )
            except Exception as e:
                print(f"Error sending welcome email: {e}")

    def __str__(self):
        return f"{self.name} ({self.account_number})"

class Transaction(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    # Using FloatField here as well for consistency
    amount = models.FloatField()
    type = models.CharField(max_length=20) # e.g., 'Deposit', 'Withdraw'
    timestamp = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.account.name} - {self.title}"