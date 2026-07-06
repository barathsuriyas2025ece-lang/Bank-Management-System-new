from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout as auth_logout, login as auth_login
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.core.mail import send_mail
from django.conf import settings
from .models import Account, Transaction, Notification
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from decimal import Decimal
from functools import wraps


def account_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, account_no, *args, **kwargs):
        current_account = request.session.get('account_no')
        if not current_account or str(current_account) != str(account_no):
            messages.error(request, 'Please login using account number and password first.')
            return redirect('login')
        return view_func(request, account_no, *args, **kwargs)
    return _wrapped_view

try:
    from twilio.rest import Client
except ImportError:
    Client = None


def send_transaction_email(request, account, subject, message):
    if account.email:
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [account.email],
                fail_silently=False,
            )
            # Add an explicit confirmation on the webpage so the user can verify the email destination
            messages.info(request, f"Email notification successfully sent to: {account.email}")
        except Exception as e:
            messages.warning(request, f"Email sending failed (Check account settings or app password). Error: {str(e)[:50]}")
    else:
        messages.warning(request, "No email configured for this account, skipping email notification.")
    return


def notify_transaction(request, account, tx_type, amount, remark=""):
    summary = f"This is an automated message from the Django Bank Project.\n\n{tx_type} transaction of ${amount:.2f} on account {account.account_number}. {remark}\n\nCurrent Balance: ${float(str(account.balance)):.2f}".strip()
    subject = f"[Django Bank Project] {tx_type} Alert: ${amount:.2f}"
    
    # Send email notification
    send_transaction_email(request, account, subject, summary)
    
    # Create in-app notification
    Notification.objects.create(account=account, title=subject, message=summary)


# 1. Login Logic
def login_page(request):
    if request.method == "POST":
        acc_no = request.POST.get('account_no')
        pw = request.POST.get('password')
        
        # First, find account just by account number
        account = Account.objects.filter(account_number=acc_no).first()

        if account:
            if account.is_frozen:
                messages.error(request, "Access Denied: Your account is frozen.")
                return render(request, 'login.html')
            
            # Check password
            if account.password == pw:
                # Reset failed attempts on successful login
                if account.failed_login_attempts > 0:
                    account.failed_login_attempts = 0
                    account.save()

                request.session['account_no'] = account.account_number
                messages.success(request, "Login successful.")
                
                return redirect('home_detail', account_no=acc_no)
            else:
                # Wrong password
                account.failed_login_attempts += 1
                if account.failed_login_attempts >= 3:
                    account.is_frozen = True
                    account.save()
                    messages.error(request, "Access Denied: Your account has been frozen due to too many failed login attempts.")
                else:
                    account.save()
                    remaining = 3 - account.failed_login_attempts
                    messages.error(request, f"Invalid credentials. You have {remaining} attempt(s) left before your account is frozen.")
                return render(request, 'login.html')
        else:
            # Account not found
            messages.error(request, "Invalid credentials.")
            return render(request, 'login.html')

    return render(request, 'login.html')

def logout_view(request):
    # logout from Django auth and clear custom session data
    auth_logout(request)
    request.session.flush()
    messages.success(request, 'Logged out successfully.')
    return redirect('login')


# 2. Fixed: Named 'home' to resolve AttributeError
@account_login_required
def home(request, account_no):
    account = get_object_or_404(Account, account_number=account_no)
    # Newest activity at the top
    transactions = account.transactions.all().order_by('-timestamp')
    notifications = account.notifications.all()[:5]
    return render(request, 'dashboard.html', {
        'account': account, 
        'transactions': transactions,
        'notifications': notifications
    })

# 3. Fixed Deposit Logic
@account_login_required
def deposit(request, account_no):
    if request.method == "POST":
        account = get_object_or_404(Account, account_number=account_no)
        
        if account.is_frozen:
            messages.error(request, "Cannot perform transactions. Your account is frozen.")
            return redirect('home_detail', account_no=account_no)
            
        amount = Decimal(str(request.POST.get('amount')))
        # Math is now compatible with Decimal128
        account.balance = Decimal(str(account.balance)) + amount
        account.save()
        Transaction.objects.create(account=account, amount=amount, type='Deposit')
        messages.success(request, f"Successfully deposited ${amount}")
        notify_transaction(request, account, 'Deposit', amount)
    return redirect('home_detail', account_no=account_no)

# 4. Fixed Withdraw Logic
@account_login_required
def withdraw(request, account_no):
    if request.method == "POST":
        account = get_object_or_404(Account, account_number=account_no)
        
        if account.is_frozen:
            messages.error(request, "Cannot perform transactions. Your account is frozen.")
            return redirect('home_detail', account_no=account_no)
            
        amount = Decimal(str(request.POST.get('amount')))
        current_bal = Decimal(str(account.balance))
        if current_bal >= amount:
            account.balance = current_bal - amount
            account.save()
            Transaction.objects.create(account=account, amount=amount, type='Withdraw')
            messages.success(request, f"Successfully withdrew ${amount}")
            notify_transaction(request, account, 'Withdraw', amount)
        else:
            messages.error(request, "Insufficient balance.")
    return redirect('home_detail', account_no=account_no)

# 5. Fixed Transfer Logic
@account_login_required
def transfer(request, account_no):
    if request.method == "POST":
        sender_account = get_object_or_404(Account, account_number=account_no)
        
        if sender_account.is_frozen:
            messages.error(request, "Cannot perform transactions. Your account is frozen.")
            return redirect('home_detail', account_no=account_no)
            
        receiver_no = request.POST.get('receiver_no')
        amount = Decimal(str(request.POST.get('amount')))
        
        receiver_account = Account.objects.filter(account_number=receiver_no).first()
        
        if not receiver_account:
            messages.error(request, "Recipient account not found.")
            return redirect('home_detail', account_no=account_no)
            
        if sender_account.account_number == receiver_account.account_number:
            messages.error(request, "You cannot transfer money to your own account.")
            return redirect('home_detail', account_no=account_no)
        
        sender_bal = Decimal(str(sender_account.balance))
        if sender_bal >= amount:
            sender_account.balance = sender_bal - amount
            sender_account.save()
            
            receiver_account.balance = Decimal(str(receiver_account.balance)) + amount
            receiver_account.save()
            
            Transaction.objects.create(account=sender_account, amount=amount, type='Transfer Out')
            Transaction.objects.create(account=receiver_account, amount=amount, type='Transfer In')
            messages.success(request, f"Successfully transferred ${amount} to {receiver_account.name}")
            notify_transaction(request, sender_account, 'Transfer Out', amount, f"to {receiver_account.account_number}")
            notify_transaction(request, receiver_account, 'Transfer In', amount, f"from {sender_account.account_number}")
        else:
            messages.error(request, "Insufficient balance for transfer.")
    return redirect('home_detail', account_no=account_no)

# 6. PDF Export

@account_login_required
def export_pdf(request, account_no):
    account = get_object_or_404(Account, account_number=account_no)
    transactions = account.transactions.all().order_by('-timestamp')
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Statement_{account_no}.pdf"'
    
    p = canvas.Canvas(response, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, f"Bank Statement: {account.name}")
    p.setFont("Helvetica", 12)
    p.drawString(100, 730, f"Balance: ${account.balance}")
    
    y = 700
    for tx in transactions:
        p.drawString(100, y, f"{tx.timestamp.strftime('%Y-%m-%d %H:%M')} - {tx.type}: ${tx.amount}")
        y -= 20
        if y < 50:
            p.showPage()
            y = 750
            
    p.showPage()
    p.save()
    return response

# 7. Freeze Account View
@account_login_required
def freeze_account(request, account_no):
    account = get_object_or_404(Account, account_number=account_no)
    account.is_frozen = True
    account.save()  # Explicitly save to database
    messages.success(request, f"Account {account_no} has been frozen.")
    return redirect('admin:accounts_account_changelist')  # Redirect to admin list

# 8. Unfreeze Account View
@account_login_required
def unfreeze_account(request, account_no):
    account = get_object_or_404(Account, account_number=account_no)
    account.is_frozen = False
    account.save()  # Explicitly save to database
    messages.success(request, f"Account {account_no} has been unfrozen.")
    return redirect('admin:accounts_account_changelist')  # Redirect to admin list

# 9. Contact Settings Page
@account_login_required
def contact_settings(request, account_no):
    account = get_object_or_404(Account, account_number=account_no)
    
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        if not phone:
            messages.error(request, "Mobile number is required.")
        else:
            # Format phone number for international format if needed
            if phone.startswith('+'):
                formatted_phone = phone
            elif phone.startswith('91') and len(phone) == 12:
                formatted_phone = '+' + phone
            elif len(phone) == 10 and phone.isdigit():
                # Assume Indian number, add +91
                formatted_phone = '+91' + phone
            else:
                formatted_phone = phone  # Keep as is if already formatted
            
            account.email = email if email else None
            account.phone = formatted_phone
            account.save()
            messages.success(request, "Contact information updated successfully.")
        
        return redirect('contact_settings', account_no=account_no)
    
    return render(request, 'contact_settings.html', {'account': account})

# 10. Security Settings Page
@account_login_required
def security_settings(request, account_no):
    account = get_object_or_404(Account, account_number=account_no)
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'change_password':
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if account.password != old_password:
                messages.error(request, "Old password is incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            elif len(new_password) < 4:
                messages.error(request, "Password must be at least 4 characters long.")
            else:
                account.password = new_password
                account.save()
                messages.success(request, "Password changed successfully.")
        
        elif action == 'freeze_account':
            account.is_frozen = True
            account.save()
            messages.warning(request, "Account frozen. You will not be able to access it until unfrozen.")
        
        elif action == 'unfreeze_account':
            account.is_frozen = False
            account.save()
            messages.success(request, "Account unfrozen successfully.")
        
        return redirect('security_settings', account_no=account_no)
    
    return render(request, 'security.html', {'account': account})