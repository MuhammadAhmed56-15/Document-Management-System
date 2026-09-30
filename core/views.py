from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q, Case, When, Value, IntegerField
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .models import Profile, Commitment, Task, NotesheetAttachment, UserHierarchy, Notification  # Saare models aik saath
from .forms import CommitmentForm, RemarkForm, TaskAssignForm
from .utils import create_notification
# =========================================================
# LOGIN VIEW (UPDATED FOR CFO)
# =========================================================
@ensure_csrf_cookie
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            profile = Profile.objects.get(user=user)
            
            # Role-based redirect
            if profile.role == "CEO":
                return redirect("ceo_dashboard")
            elif profile.role == "PS":
                return redirect("ps_dashboard")
            elif profile.role == "GM":
                return redirect("gm_dashboard")
            elif profile.role in ["Manager", "ZM", "AM", "IT", "CFO", "HR", "Auditor", "Officer"]:
                return redirect("manager_dashboard")
            else:
                # Fallback: redirect to manager_dashboard for any other role
                return redirect("manager_dashboard")
        else:
            messages.error(request, "Invalid username or password")
    return render(request, "login.html")

# =========================================================
# LOGOUT VIEW
# =========================================================
@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

# =========================================================
# PS DASHBOARD
# =========================================================
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta, datetime
from .models import Profile, Commitment
import json

@login_required
def ps_dashboard(request):
    profile = Profile.objects.get(user=request.user)
    if profile.role != "PS":
        if profile.role == "CEO":
            return redirect("ceo_dashboard")
        elif profile.role == "GM":
            return redirect("gm_dashboard")
        else:
            return redirect("manager_dashboard")

    # KPI counts
    total = Commitment.objects.filter(created_by=profile).count()
    pending = Commitment.objects.filter(created_by=profile, status="Pending").count()
    approved = Commitment.objects.filter(created_by=profile, status="Approved").count()
    rejected = Commitment.objects.filter(created_by=profile, status="Rejected").count()

    # Lists for modal display
    all_commitments = Commitment.objects.filter(created_by=profile).order_by('-commitment_date')
    pending_list = Commitment.objects.filter(created_by=profile, status="Pending").order_by('-commitment_date')
    approved_list = Commitment.objects.filter(created_by=profile, status="Approved").order_by('-commitment_date')
    rejected_list = Commitment.objects.filter(created_by=profile, status="Rejected").order_by('-commitment_date')

    # Convert querysets to JSON for JavaScript
    def commitment_to_dict(c):
        # handle date vs datetime comparisons safely
        is_overdue = False
        if c.commitment_date:
            try:
                if hasattr(c.commitment_date, 'hour'):
                    is_overdue = (c.commitment_date < timezone.now() and c.status != 'Completed')
                else:
                    is_overdue = (c.commitment_date < timezone.now().date() and c.status != 'Completed')
            except Exception:
                is_overdue = False

        return {
            'id': c.id,
            'title': c.title,
            'description': c.description,
            'location': c.location,
            'category': c.category,
            'status': c.status,
            'date': c.commitment_date.strftime('%b %d, %Y'),
            'time': c.commitment_date.strftime('%I:%M %p'),
            'datetime': c.commitment_date.strftime('%Y-%m-%d %H:%M'),
            'is_overdue': is_overdue
        }

    all_commitments_json = json.dumps([commitment_to_dict(c) for c in all_commitments])
    pending_list_json = json.dumps([commitment_to_dict(c) for c in pending_list])
    approved_list_json = json.dumps([commitment_to_dict(c) for c in approved_list])
    rejected_list_json = json.dumps([commitment_to_dict(c) for c in rejected_list])

    today = timezone.now()
    next_week = today + timedelta(days=7)

    upcoming = Commitment.objects.filter(
        created_by=profile,
        commitment_date__range=(today, next_week)
    ).order_by('commitment_date')

    # Commitment category / daily charts
    category_counts = Commitment.objects.filter(created_by=profile).values('category').annotate(count=Count('id'))
    category_labels = [item['category'] for item in category_counts]
    category_data = [item['count'] for item in category_counts]

    daily_labels = []
    daily_data = []
    for i in range(7):
        day = today + timedelta(days=i)
        daily_labels.append(day.strftime("%Y-%m-%d"))
        cnt = Commitment.objects.filter(created_by=profile, commitment_date__date=day.date()).count()
        daily_data.append(cnt)

    com_category_counts = Commitment.objects.filter(created_by=profile).values('category').annotate(count=Count('id'))
    com_category_labels = [item['category'] if item['category'] else 'Uncategorized' for item in com_category_counts]
    com_category_data = [item['count'] for item in com_category_counts]

    # ============================================================
    # NOTESHEET DATA
    # ============================================================
    from django.db.models import Q
    from .models import Notesheet, NotesheetForward, File, Letter, Task

    ns_files = File.objects.filter(created_by=request.user).order_by('-created_at')
    ns_inbox = Notesheet.objects.filter(current_holder=request.user).order_by('-updated_at')
    ns_forwarded_ids = NotesheetForward.objects.filter(forwarded_by=request.user).values_list('notesheet_id', flat=True)
    ns_outbox = Notesheet.objects.filter(
        Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).exclude(current_holder=request.user).distinct().order_by('-updated_at')

    ns_total_count = Notesheet.objects.filter(
        Q(current_holder=request.user) | Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).distinct().count()

    ns_status_counts = {'Files': ns_files.count(), 'Inbox': ns_inbox.count(), 'Outbox': ns_outbox.count()}
    ns_category_labels = list(ns_status_counts.keys())
    ns_category_data = list(ns_status_counts.values())

    # ============================================================
    # TASK DATA
    # ============================================================
    tasks_total = Task.objects.filter(
        Q(assigned_to=request.user) | Q(assigned_by=request.user)
    ).distinct().order_by('-created_at')
    tasks_pending = tasks_total.exclude(status='Completed').order_by('-created_at')
    tasks_completed = tasks_total.filter(status='Completed').order_by('-created_at')
    tasks_overdue = tasks_total.filter(due_date__lt=today.date()).exclude(status='Completed').order_by('-created_at')
    upcoming_tasks = tasks_total.filter(
        due_date__range=(today.date(), next_week.date())
    ).exclude(status='Completed').order_by('due_date')
    task_status_counts = tasks_total.values('status').annotate(count=Count('id'))
    task_category_labels = [item['status'] if item['status'] else 'Uncategorized' for item in task_status_counts]
    task_category_data = [item['count'] for item in task_status_counts]

    # ============================================================
    # LETTER DATA
    # ============================================================
    letters_total = Letter.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user)
    ).distinct().order_by('-created_at')
    letters_inbox = Letter.objects.filter(receiver=request.user, is_draft=False).order_by('-created_at')
    letters_outbox = Letter.objects.filter(sender=request.user, is_draft=False).order_by('-created_at')
    letters_drafts = Letter.objects.filter(sender=request.user, is_draft=True).order_by('-created_at')

    letters_drafts_count = letters_drafts.count()
    letters_inbox_count = letters_inbox.count()
    letters_outbox_count = letters_outbox.count()
    letters_total_count = letters_total.count()
    letter_category_labels = ['Inbox', 'Outbox', 'Drafts']
    letter_category_data = [letters_inbox_count, letters_outbox_count, letters_drafts_count]

    context = {
        # Legacy commitment keys (keep for backward compat)
        "total": total, "pending": pending, "approved": approved, "rejected": rejected,
        "all_commitments_json": all_commitments_json,
        "pending_list_json": pending_list_json,
        "approved_list_json": approved_list_json,
        "rejected_list_json": rejected_list_json,
        "approved_list": approved_list,
        "upcoming": upcoming,
        "category_labels": category_labels,
        "category_data": category_data,
        "daily_labels": daily_labels,
        "daily_data": daily_data,

        # CEO-style commitment keys
        "com_total": total, "com_pending": pending, "com_approved": approved, "com_rejected": rejected,
        "com_total_list": all_commitments,
        "com_pending_list": pending_list,
        "com_approved_list": approved_list,
        "com_rejected_list": rejected_list,
        "com_category_labels": com_category_labels,
        "com_category_data": com_category_data,

        # Notesheets
        "ns_total_count": ns_total_count,
        "ns_files_count": ns_files.count(), "ns_inbox_count": ns_inbox.count(), "ns_outbox_count": ns_outbox.count(),
        "ns_files_list": ns_files, "ns_inbox_list": ns_inbox, "ns_outbox_list": ns_outbox,
        "ns_category_labels": ns_category_labels, "ns_category_data": ns_category_data,

        # Tasks
        "tasks_total_count": tasks_total.count(), "tasks_pending_count": tasks_pending.count(),
        "tasks_completed_count": tasks_completed.count(), "tasks_overdue_count": tasks_overdue.count(),
        "tasks_total_list": tasks_total, "tasks_pending_list": tasks_pending,
        "tasks_completed_list": tasks_completed, "tasks_overdue_list": tasks_overdue,
        "upcoming_tasks": upcoming_tasks,
        "task_category_labels": task_category_labels, "task_category_data": task_category_data,

        # Letters
        "letters_total_count": letters_total_count, "letters_drafts_count": letters_drafts_count,
        "letters_outbox_count": letters_outbox_count, "letters_inbox_count": letters_inbox_count,
        "letters_total_list": letters_total, "letters_drafts_list": letters_drafts,
        "letters_outbox_list": letters_outbox, "letters_inbox_list": letters_inbox,
        "letter_category_labels": letter_category_labels, "letter_category_data": letter_category_data,
    }
    return render(request, "ps_dashboard.html", context)

# =========================================================
# PS CHART DATA API - ENDPOINT FOR DYNAMIC CHART
# =========================================================
@login_required
def get_ps_chart_data(request):
    """
    API endpoint to get PS chart data for specific date ranges.
    Supports sections: notesheet, commitment, task, letter
    Usage: /api/ps-chart-data/?dates=2026-01-22,2026-01-23&section=notesheet
    """
    from .models import Notesheet, Task, Letter
    profile = Profile.objects.get(user=request.user)
    if profile.role != "PS":
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    dates_str = request.GET.get('dates', '')
    section   = request.GET.get('section', 'commitment')

    if not dates_str:
        return JsonResponse({'error': 'No dates provided'}, status=400)

    dates = dates_str.split(',')
    data  = []

    for date_str in dates:
        try:
            date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
            if section == 'notesheet':
                count = Notesheet.objects.filter(created_by=request.user, created_at__date=date).count()
            elif section == 'task':
                from django.db.models import Q as _Q
                count = Task.objects.filter(
                    _Q(assigned_to=request.user) | _Q(assigned_by=request.user),
                    created_at__date=date
                ).distinct().count()
            elif section == 'letter':
                count = Letter.objects.filter(sender=request.user, created_at__date=date).count()
            else:
                count = Commitment.objects.filter(created_by=profile, commitment_date__date=date).count()
            data.append(count)
        except ValueError:
            data.append(0)

    return JsonResponse(data, safe=False)

# =========================================================
# CEO DASHBOARD 
# =========================================================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta, datetime
from .models import Profile, Commitment, Task, User
from .forms import CommitmentForm, TaskAssignForm

@login_required
def ceo_dashboard(request):
    from django.db.models import Q
    from django.db.models import Count
    from .models import Notesheet, NotesheetForward, File, Letter, LetterFile, Task, Commitment, Profile

    profile = Profile.objects.get(user=request.user)
    if profile.role != "CEO":
        if profile.role == "PS":
            return redirect("ps_dashboard")
        elif profile.role == "GM":
            return redirect("gm_dashboard")
        else:
            return redirect("manager_dashboard")

    today = timezone.now()
    next_week = today + timedelta(days=7)

    # 1. Commitments Data (Whole system base)
    com_total_list = Commitment.objects.all()
    com_pending_list = Commitment.objects.filter(status__iexact="Pending")
    com_approved_list = Commitment.objects.filter(status__iexact="Approved")
    com_rejected_list = Commitment.objects.filter(status__iexact="Rejected")

    upcoming = Commitment.objects.filter(
        commitment_date__range=(today, next_week), 
        status__iexact="Approved"
    ).order_by('commitment_date')

    # Commitments Category breakdown for Pie Chart
    com_category_counts = Commitment.objects.values('category').annotate(count=Count('id'))
    com_category_labels = [item['category'] if item['category'] else 'Uncategorized' for item in com_category_counts]
    com_category_data = [item['count'] for item in com_category_counts]

    # 2. Notesheets Data (My files, My inbox, My outbox)
    ns_files = File.objects.filter(created_by=request.user).order_by('-created_at')
    ns_inbox = Notesheet.objects.filter(current_holder=request.user).order_by('-updated_at')
    
    ns_forwarded_ids = NotesheetForward.objects.filter(forwarded_by=request.user).values_list('notesheet_id', flat=True)
    ns_outbox = Notesheet.objects.filter(
        Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).exclude(current_holder=request.user).distinct().order_by('-updated_at')

    # Notesheet total in hand or created
    ns_total_count = Notesheet.objects.filter(
        Q(current_holder=request.user) | Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).distinct().count()

    # Notesheet status count for Pie chart
    ns_status_counts = {
        'Files': ns_files.count(),
        'Inbox': ns_inbox.count(),
        'Outbox': ns_outbox.count()
    }
    ns_category_labels = list(ns_status_counts.keys())
    ns_category_data = list(ns_status_counts.values())

    # 3. Tasks Data (Whole system)
    tasks_total = Task.objects.all().order_by('-created_at')
    tasks_pending = Task.objects.exclude(status='Completed').order_by('-created_at')
    tasks_completed = Task.objects.filter(status='Completed').order_by('-created_at')
    
    # Overdue Tasks (due_date < today and not completed)
    tasks_overdue = Task.objects.filter(
        due_date__lt=today.date()
    ).exclude(status='Completed').order_by('-created_at')

    # Upcoming Tasks (Next 7 days, pending/seen/in progress)
    upcoming_tasks = Task.objects.filter(
        due_date__range=(today.date(), next_week.date())
    ).exclude(status='Completed').order_by('due_date')

    # Task Status breakdown for Pie Chart
    task_status_counts = Task.objects.values('status').annotate(count=Count('id'))
    task_category_labels = [item['status'] if item['status'] else 'Uncategorized' for item in task_status_counts]
    task_category_data = [item['count'] for item in task_status_counts]

    # 4. Letters Data (Whole system)
    letters_total = Letter.objects.all().order_by('-created_at')
    letters_inbox = Letter.objects.filter(receiver=request.user, is_draft=False).order_by('-created_at')
    letters_outbox = Letter.objects.filter(sender=request.user, is_draft=False).order_by('-created_at')
    letters_drafts = Letter.objects.filter(sender=request.user, is_draft=True).order_by('-created_at')
    
    letters_drafts_count = letters_drafts.count()
    letters_inbox_count = letters_inbox.count()
    letters_outbox_count = letters_outbox.count()
    letters_total_count = letters_total.count()

    # Letter status breakdown (Inbox vs Outbox vs Drafts) for Pie Chart
    letter_category_labels = ['Inbox', 'Outbox', 'Drafts']
    letter_category_data = [letters_inbox_count, letters_outbox_count, letters_drafts_count]

    # Render context
    context = {
        # Commitments lists/counts
        "com_total": com_total_list.count(),
        "com_pending": com_pending_list.count(),
        "com_approved": com_approved_list.count(),
        "com_rejected": com_rejected_list.count(),
        "com_total_list": com_total_list,
        "com_pending_list": com_pending_list,
        "com_approved_list": com_approved_list,
        "com_rejected_list": com_rejected_list,
        "upcoming": upcoming,
        "com_category_labels": com_category_labels,
        "com_category_data": com_category_data,

        # Notesheets lists/counts
        "ns_total_count": ns_total_count,
        "ns_files_count": ns_files.count(),
        "ns_inbox_count": ns_inbox.count(),
        "ns_outbox_count": ns_outbox.count(),
        "ns_files_list": ns_files,
        "ns_inbox_list": ns_inbox,
        "ns_outbox_list": ns_outbox,
        "ns_category_labels": ns_category_labels,
        "ns_category_data": ns_category_data,

        # Tasks lists/counts
        "tasks_total_count": tasks_total.count(),
        "tasks_pending_count": tasks_pending.count(),
        "tasks_completed_count": tasks_completed.count(),
        "tasks_overdue_count": tasks_overdue.count(),
        "tasks_total_list": tasks_total,
        "tasks_pending_list": tasks_pending,
        "tasks_completed_list": tasks_completed,
        "tasks_overdue_list": tasks_overdue,
        "upcoming_tasks": upcoming_tasks,
        "task_category_labels": task_category_labels,
        "task_category_data": task_category_data,

        # Letters lists/counts
        "letters_total_count": letters_total_count,
        "letters_drafts_count": letters_drafts_count,
        "letters_outbox_count": letters_outbox_count,
        "letters_inbox_count": letters_inbox_count,
        "letters_total_list": letters_total,
        "letters_drafts_list": letters_drafts,
        "letters_outbox_list": letters_outbox,
        "letters_inbox_list": letters_inbox,
        "letter_category_labels": letter_category_labels,
        "letter_category_data": letter_category_data,
    }

    return render(request, "ceo_dashboard.html", context)

# =========================================================
# CHART DATA API - FOR DYNAMIC CHART
# =========================================================
@login_required
def get_chart_data(request):
    """API endpoint to get chart data for specific date ranges"""
    from datetime import datetime
    from .models import Commitment, Notesheet, Task, Letter, Profile
    
    profile = Profile.objects.get(user=request.user)
    if profile.role not in ["CEO", "Manager", "ZM", "AM", "IT", "CFO", "HR", "GM", "Auditor", "PS"]:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    dates_str = request.GET.get('dates', '')
    section = request.GET.get('section', 'commitment')
    
    if not dates_str:
        return JsonResponse({'error': 'No dates provided'}, status=400)
    
    dates = dates_str.split(',')
    data = []
    
    for date_str in dates:
        try:
            date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
            if section == 'notesheet':
                initiated = Notesheet.objects.filter(created_by=request.user, created_at__date=date).count()
                data.append(initiated)
            elif section == 'task':
                if profile.role == 'CEO':
                    created = Task.objects.filter(created_at__date=date).count()
                else:
                    created = Task.objects.filter(assigned_to=request.user, created_at__date=date).count()
                data.append(created)
            elif section == 'letter':
                sent = Letter.objects.filter(sender=request.user, created_at__date=date).count()
                data.append(sent)
            elif section == 'requisition':
                from .models import VehicleRequisition
                count = VehicleRequisition.objects.filter(created_at__date=date).count()
                data.append(count)
            else:
                count = Commitment.objects.filter(
                    commitment_date__date=date,
                    status__iexact="Approved"
                ).count()
                data.append(count)
        except ValueError:
            data.append(0)
    
    return JsonResponse(data, safe=False)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Profile, Commitment
from .forms import CommitmentForm


# =========================================================
# 1. ADD COMMITMENT
# =========================================================
@login_required
def add_commitment(request):
    profile = get_object_or_404(Profile, user=request.user)

    managers = User.objects.filter(
        Q(profile__role__category="Manager") | Q(profile__role__code="Manager")
    ).select_related("profile")

    if request.method == "POST":
        form = CommitmentForm(request.POST, user=request.user)
        if form.is_valid():
            commitment = form.save(commit=False)
            commitment.created_by = profile

            # PS add kare toh 'Pending', CEO add kare toh direkt 'Approved'
            if profile.role == "PS":
                commitment.status = "Pending"
            elif profile.role == "CEO":
                commitment.status = "Approved"

            commitment.save()

            invited_ids = request.POST.getlist("invited_managers")
            commitment.invited_managers.set(invited_ids)

            for user_id in invited_ids:
                try:
                    manager_user = User.objects.get(id=user_id)
                    create_notification(
                        recipient=manager_user,
                        sender=request.user,
                        title="New Commitment Assigned",
                        message=f"You have been assigned to a new commitment: '{commitment.title}' by {request.user.username}",
                        link=f"/commitment/list/",
                        notification_type='commitment'
                    )
                except User.DoesNotExist:
                    pass

            messages.success(request, "Commitment added successfully!")
            return redirect("ceo_dashboard" if profile.role == "CEO" else "ps_dashboard")
    else:
        form = CommitmentForm(user=request.user)

    return render(request, "add_commitment.html", {"form": form, "managers": managers})


# =========================================================
# 2. EDIT COMMITMENT
# =========================================================
@login_required
def edit_commitment(request, pk):
    profile = get_object_or_404(Profile, user=request.user)
    commitment = get_object_or_404(Commitment, pk=pk)

    if commitment.is_expired and profile.role != "CEO":
        messages.error(request, "Cannot edit expired commitments!")
        return redirect("ps_dashboard" if profile.role == "PS" else "commitment_list")

    if profile.role == "CEO" or commitment.created_by == profile:
        if request.method == "POST":
            form = CommitmentForm(request.POST, instance=commitment, user=request.user)
            if form.is_valid():
                updated_commitment = form.save(commit=False)
                if profile.role == "PS":
                    updated_commitment.status = "Pending"
                updated_commitment.save()
                form.save_m2m()

                messages.success(request, "Commitment updated successfully!")
                return redirect("ceo_dashboard" if profile.role == "CEO" else "ps_dashboard")
        else:
            form = CommitmentForm(instance=commitment, user=request.user)

        return render(request, "edit_commitment.html", {"form": form, "commitment": commitment})
    else:
        messages.error(request, "You are not authorized to edit this!")
        return redirect("ps_dashboard")


# =========================================================
# 3. UPDATE STATUS (CEO Approval Action)
# =========================================================
@login_required
def update_status(request, pk, status):
    """CEO approves or rejects a commitment"""
    profile = get_object_or_404(Profile, user=request.user)
    if profile.role != "CEO":
        messages.error(request, "Not authorized")
        return redirect("ps_dashboard")

    commitment = get_object_or_404(Commitment, pk=pk)
    if status in ["Approved", "Rejected"]:
        commitment.status = status
        commitment.save()


        messages.success(request, f"Commitment {status.lower()} successfully!")
    return redirect("ceo_dashboard")


# =========================================================
# 4. DELETE COMMITMENT
# =========================================================
@login_required
def delete_commitment(request, pk):
    profile = get_object_or_404(Profile, user=request.user)
    commitment = get_object_or_404(Commitment, pk=pk)

    if profile.role == "CEO" or commitment.created_by == profile:
        commitment.delete()
        messages.success(request, "Deleted successfully!")
    else:
        messages.error(request, "You cannot delete this!")

    return redirect("ceo_dashboard" if profile.role == "CEO" else "ps_dashboard")


# =========================================================
# 5. COMMITMENT LIST (ALL COMMITMENTS FOR CEO & PS)
# =========================================================
@login_required
def commitment_list(request):
    profile = get_object_or_404(Profile, user=request.user)
    today = timezone.now()
    status_filter = request.GET.get('status')

    # Quick Inline Approval Logic (CEO Modal / Table Actions)
    if profile.role == "CEO" and request.method == "POST":
        commitment_id = request.POST.get("commitment_id")
        action = request.POST.get("action")
        try:
            commitment = Commitment.objects.get(id=commitment_id)
            if action == "approve":
                commitment.status = "Approved"
            elif action == "reject":
                commitment.status = "Rejected"
            commitment.save()
            messages.success(request, f"Commitment {commitment.status.lower()} successfully!")
        except Commitment.DoesNotExist:
            pass
        return redirect("commitment_list")

    # ── FIXED QUERY LOGIC ──
    # CEO aur PS DONO ko TAMAM Commitments show hongi
    if profile.role in ["CEO", "PS"]:
        commitments = Commitment.objects.select_related('created_by__user').all().order_by('-created_at')
    else:
        commitments = Commitment.objects.none()

    # Status filter (Agar user dropdown filtering use kare)
    if status_filter and status_filter != 'All':
        commitments = commitments.filter(status=status_filter)

    return render(request, 'commitment_list.html', {
        'commitments': commitments,
        'today': today,
        'profile': profile,
    })

@login_required
def commitment_report(request):
    profile = Profile.objects.get(user=request.user)

    if profile.role == "CEO":
        commitments = Commitment.objects.all().order_by('-commitment_date')
    elif profile.role == "PS":
        commitments = Commitment.objects.filter(created_by=profile).order_by('-commitment_date')
    else:
        commitments = Commitment.objects.none()

    status_filter = request.GET.get('status')
    category_filter = request.GET.get('category')
    priority_filter = request.GET.get('priority')
    search_query = request.GET.get('search')

    if status_filter and status_filter != 'All':
        commitments = commitments.filter(status=status_filter)
    if category_filter and category_filter != 'All':
        commitments = commitments.filter(category=category_filter)
    if priority_filter and priority_filter != 'All':
        commitments = commitments.filter(priority=priority_filter)
    if search_query:
        commitments = commitments.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        )

    context = {
        'commitments': commitments,
        'status_choices': ['All'] + [choice[0] for choice in Commitment.STATUS_CHOICES],
        'category_choices': ['All', 'Meeting', 'Visit', 'Event'],
        'priority_choices': ['All', 'Normal', 'High'],
        'selected_status': status_filter or 'All',
        'selected_category': category_filter or 'All',
        'selected_priority': priority_filter or 'All',
        'search_query': search_query or ''
    }
    return render(request, 'report.html', context)

@login_required
def approve_commitment(request, id):
    commitment = get_object_or_404(Commitment, id=id)
    commitment.status = "Approved"
    commitment.save()
    return redirect("manager_dashboard")

@login_required
def reject_commitment(request, id):
    commitment = get_object_or_404(Commitment, id=id)
    commitment.status = "Rejected"
    commitment.save()
    return redirect("manager_dashboard")

# =========================================================
# TASK MODULE (Line 547 se Aage Fully Fixed Code)
# =========================================================

# 1. ASSIGN / ADD TASK VIEW
@login_required
def assign_task_view(request):
    role = getattr(request.user.profile, 'role', '')
    
    # Removed ZM Users restriction to allow access


    # Dynamic Dropdown Filters
    username_upper = request.user.username.upper()
    if role == 'CFO':
        filtered_users = User.objects.filter(username__in=['FINANCE_MANAGER', 'BILLING_MANAGER'])
    elif role == 'CEO':
        filtered_users = User.objects.exclude(id=request.user.id)
    elif role == 'GM_HR' or username_upper == 'GM_HR':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_Hr')
    elif username_upper == 'PROJECT_MANAGER':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_Pro')
    elif username_upper == 'FINANCE_MANAGER':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_Finance')
    elif username_upper == 'MANAGER_MEDIA':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_Media')
    elif username_upper == 'BILLING_MANAGER':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_Billing')
    elif username_upper == 'AUDIT_MANAGER':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_Audit')
    elif username_upper == 'MANAGER_PMER':
        filtered_users = User.objects.filter(username__iexact='Asis_Manager_PMER')
    elif username_upper == 'FLEET_MANAGER':
        filtered_users = User.objects.filter(username__in=['Fleet_Officer_A', 'Fleet_Officer_B', 'Fleet_Officer_C', 'Fleet_Officer_D', 'Fleet_Officer_E'])
    else:
        hierarchy = UserHierarchy.objects.filter(boss=request.user).first()
        if hierarchy and hierarchy.task_subs.exists():
            filtered_users = hierarchy.task_subs.all()
        else:
            filtered_users = User.objects.exclude(id=request.user.id)
            
        if role in ['CEO', 'GM'] and username_upper != 'GM_HR':
            cfo_user = User.objects.filter(username='CFO')
            filtered_users = (filtered_users | cfo_user).distinct()

    if request.method == "POST":
        form = TaskAssignForm(request.POST)
        form.fields['assigned_to'].queryset = filtered_users
        
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = request.user 
            task.save()
            task.save()
            
            create_notification(
                recipient=task.assigned_to,
                sender=request.user,
                title="New Task Assigned",
                message=f"You have been assigned a new task: '{task.title}' by {request.user.username}",
                link="/manager/tasks/",
                notification_type='task'
            )
            
            messages.success(request, f"Task '{task.title}' has been successfully assigned to {task.assigned_to.username}!")
            return redirect('all_tasks')
    else:
        form = TaskAssignForm()
        form.fields['assigned_to'].queryset = filtered_users
    
    return render(request, 'ceo_assign_task.html', {
        'form': form,
        'user_role': role
    })

# Aliases for Assign Task
add_task_view = assign_task_view


# 2. MY TASKS (INBOX)
@login_required
def manager_task_view(request):
    status_filter = request.GET.get('status')
    
    # Jo tasks CURRENT LOGIN USER ko assign hue hain
    base_tasks = Task.objects.filter(assigned_to=request.user)

    # Mark as Seen automatically
    unseen_tasks = base_tasks.filter(is_seen=False)
    if unseen_tasks.exists():
        unseen_tasks.update(is_seen=True, seen_at=timezone.now())

    tasks = base_tasks.order_by('-created_at')

    if status_filter and status_filter.lower() != 'all':
        tasks = tasks.filter(status__iexact=status_filter)

    context = {
        'tasks': tasks,
        'selected_status': status_filter,
        'total_count': base_tasks.count(),
        'pending_count': base_tasks.filter(status='Pending').count(),
        'in_progress_count': base_tasks.filter(status='In Progress').count(),
        'completed_count': base_tasks.filter(status='Completed').count(),
        'page_title': 'My Tasks (Inbox)'
    }
    
    return render(request, 'manager_tasks.html', context)

# Aliases for Manager Tasks
my_tasks_view = manager_task_view


# 3. SENT TASKS / ALL TASKS (OUTBOX)
@login_required
def sent_tasks_view(request):
    tasks = Task.objects.filter(assigned_by=request.user).order_by('-created_at')

    query = request.GET.get('q')
    if query:
        tasks = tasks.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query) |
            Q(assigned_to__username__icontains=query)
        )

    status_filter = request.GET.get('status')
    if status_filter and status_filter.lower() != 'all':
        tasks = tasks.filter(status__iexact=status_filter)

    return render(request, 'all_tasks_list.html', {
        'tasks': tasks,
        'user_role': request.user.profile.role,
        'page_title': 'Sent Tasks (Assigned by Me)'
    })

# Aliases for All Tasks / Sent Tasks
all_tasks_view = sent_tasks_view


# 4. TASK FEEDBACKS VIEW
@login_required
def task_feedbacks_view(request):
    user_role = request.user.profile.role
    
    if user_role == 'CEO':
        feedback_tasks = Task.objects.filter(assigned_by=request.user, remarks__isnull=False)
    else:
        feedback_tasks = Task.objects.filter(
            Q(assigned_by=request.user) | Q(assigned_to=request.user),
            remarks__isnull=False
        )

    feedback_tasks = feedback_tasks.distinct().order_by('-created_at')

    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'all')

    if query:
        feedback_tasks = feedback_tasks.filter(
            Q(title__icontains=query) | 
            Q(assigned_to__username__icontains=query) |
            Q(assigned_by__username__icontains=query)
        )

    if status_filter and status_filter.lower() != 'all':
        feedback_tasks = feedback_tasks.filter(status__iexact=status_filter)

    export_format = request.GET.get('export')
    if export_format == 'excel':
        data = []
        for task in feedback_tasks:
            last_remark = task.remarks.last()
            feedback_text = last_remark.feedback if last_remark else "No Feedback"
            attachment_urls = []
            if last_remark:
                for n in (1, 2, 3):
                    f = getattr(last_remark, f'attachment_{n}', None)
                    if f:
                        attachment_urls.append(request.build_absolute_uri(f.url))
            file_url = ', '.join(attachment_urls) if attachment_urls else "No Attachment"

            data.append({
                'Task Name': task.title,
                'Assigned By': task.assigned_by.username,
                'Assigned To': task.assigned_to.username if task.assigned_to else "N/A",
                'Feedback': feedback_text,
                'Attachment Link': file_url,
                'Due Date': task.due_date.strftime('%Y-%m-%d') if task.due_date else "N/A",
                'Status': task.status
            })
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{user_role}_Task_Feedbacks.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return response

    if export_format == 'pdf':
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{user_role}_Task_Feedbacks.pdf"'
        doc = SimpleDocTemplate(response, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()
        elements.append(Paragraph(f"{user_role} Task Feedback Report", styles['Title']))
        
        data = [['Task Name', 'Assigned To', 'Feedback', 'Attachment Link', 'Status']]
        for task in feedback_tasks:
            last_remark = task.remarks.last()
            fb = last_remark.feedback if last_remark else "No Feedback"
            staff = task.assigned_to.username if task.assigned_to else "N/A"
            attachment_urls = []
            if last_remark:
                for n in (1, 2, 3):
                    f = getattr(last_remark, f'attachment_{n}', None)
                    if f:
                        attachment_urls.append(request.build_absolute_uri(f.url))
            file_url = ', '.join(attachment_urls) if attachment_urls else "No Attachment"
            data.append([task.title, staff, fb, file_url, task.status])
        
        feedback_table = Table(data, repeatRows=1)
        feedback_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6f42c1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(feedback_table)
        doc.build(elements)
        return response

    return render(request, 'ceo_view_feedbacks.html', {
        'feedbacks': feedback_tasks,
        'query': query,
        'status_filter': status_filter,
        'user_role': user_role
    })

# Aliases for Feedbacks
view_feedbacks = task_feedbacks_view


# 5. ADD REMARK / FEEDBACK VIEW
@login_required
def add_remark_view(request):
    role = request.user.profile.role
    username_upper = request.user.username.upper()

    from .forms import RemarkForm
    from .models import Remark, RemarkAttachment
    
    if request.method == "POST":
        form = RemarkForm(request.POST, request.FILES, manager=request.user) 
        
        if form.is_valid():
            task_obj = form.cleaned_data.get('task')
            # Prevent double submission
            if Remark.objects.filter(task=task_obj, manager=request.user).exists():
                messages.info(request, "Feedback already submitted for this task.")
                return redirect('manager_tasks')
            cd = form.cleaned_data
            remark = Remark(
                task=cd.get('task'),
                manager=request.user,
                feedback=cd.get('feedback'),
                action_taken=cd.get('action_taken')
            )

            uploaded_files = request.FILES.getlist('attachments') if request.FILES else []
            max_file_size = 50 * 1024 * 1024
            allowed_ext = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.png', '.jpg', '.jpeg')
            
            for f in uploaded_files:
                if f.size > max_file_size:
                    messages.error(request, f"File '{f.name}' exceeds the 50MB limit.")
                    return render(request, 'add_remark.html', {'form': form})
                if not f.name.lower().endswith(allowed_ext):
                    messages.error(request, f"Unsupported file type: {f.name}")
                    return render(request, 'add_remark.html', {'form': form})

            # For backward compatibility: populate attachment_1, attachment_2, attachment_3
            for idx, field_name in enumerate(('attachment_1', 'attachment_2', 'attachment_3')):
                if idx < len(uploaded_files):
                    setattr(remark, field_name, uploaded_files[idx])
            
            remark.save()

            # Save all files to RemarkAttachment
            for f in uploaded_files:
                RemarkAttachment.objects.create(remark=remark, file=f)
            
            task = cd.get('task')
            if remark.action_taken == 'approve':
                task.status = 'Completed'
            else:
                task.status = 'In Progress'
            task.save()

            messages.success(request, "Feedback submitted successfully!")
            return redirect('manager_tasks')
    else:
        task_id = request.GET.get('task_id')
        if task_id:
            from .models import Remark
            if Remark.objects.filter(task_id=task_id, manager=request.user).exists():
                messages.info(request, "Feedback already submitted for this task.")
                return redirect('manager_tasks')
        initial_data = {'task': task_id} if task_id else {}
        form = RemarkForm(manager=request.user, initial=initial_data)

    return render(request, 'add_remark.html', {'form': form})


@login_required
def task_feedback_detail_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    role = getattr(request.user.profile, 'role', '')
    
    if not (task.assigned_to == request.user or task.assigned_by == request.user or role in ['CEO', 'PS']):
        return HttpResponseForbidden("You are not authorized to view feedbacks for this task.")

    remarks = task.remarks.all().order_by('created_at')

    return render(request, 'task_feedback_detail.html', {
        'task': task,
        'remarks': remarks,
        'user_role': role
    })


# 6. MANAGER DASHBOARD VIEW
@login_required
def manager_dashboard(request):
    from django.db.models import Q, Count
    from .models import Notesheet, NotesheetForward, File, Letter, Task, Commitment, Profile

    today = timezone.now()
    next_week = today + timedelta(days=7)

    # 1. Notesheets Data (My files, My inbox, My outbox)
    ns_files = File.objects.filter(created_by=request.user).order_by('-created_at')
    ns_inbox = Notesheet.objects.filter(current_holder=request.user).order_by('-updated_at')
    
    ns_forwarded_ids = NotesheetForward.objects.filter(forwarded_by=request.user).values_list('notesheet_id', flat=True)
    ns_outbox = Notesheet.objects.filter(
        Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).exclude(current_holder=request.user).distinct().order_by('-updated_at')

    ns_total_count = Notesheet.objects.filter(
        Q(current_holder=request.user) | Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).distinct().count()

    ns_status_counts = {
        'Files': ns_files.count(),
        'Inbox': ns_inbox.count(),
        'Outbox': ns_outbox.count()
    }
    ns_category_labels = list(ns_status_counts.keys())
    ns_category_data = list(ns_status_counts.values())

    # 2. Tasks Data (Only tasks assigned to manager)
    my_tasks = Task.objects.filter(assigned_to=request.user)
    
    tasks_total = my_tasks.order_by('-created_at')
    tasks_pending = my_tasks.exclude(status='Completed').order_by('-created_at')
    tasks_completed = my_tasks.filter(status='Completed').order_by('-created_at')
    tasks_overdue = my_tasks.filter(due_date__lt=today.date()).exclude(status='Completed').order_by('-created_at')
    
    upcoming_tasks = my_tasks.filter(
        due_date__range=(today.date(), next_week.date())
    ).exclude(status='Completed').order_by('due_date')

    task_status_counts = my_tasks.values('status').annotate(count=Count('id'))
    task_category_labels = [item['status'] if item['status'] else 'Uncategorized' for item in task_status_counts]
    task_category_data = [item['count'] for item in task_status_counts]

    # 3. Letters Data (My letters)
    letters_inbox = Letter.objects.filter(receiver=request.user, is_draft=False).order_by('-created_at')
    letters_outbox = Letter.objects.filter(sender=request.user, is_draft=False).order_by('-created_at')
    letters_drafts = Letter.objects.filter(sender=request.user, is_draft=True).order_by('-created_at')
    
    letters_total = list(letters_inbox) + list(letters_outbox) + list(letters_drafts)
    
    letters_drafts_count = letters_drafts.count()
    letters_inbox_count = letters_inbox.count()
    letters_outbox_count = letters_outbox.count()
    letters_total_count = len(letters_total)

    letter_category_labels = ['Inbox', 'Outbox', 'Drafts']
    letter_category_data = [letters_inbox_count, letters_outbox_count, letters_drafts_count]

    # Requisitions Data (Only if Fleet_Manager)
    req_total_count = 0
    req_pending_count = 0
    req_approved_count = 0
    req_completed_count = 0
    req_rejected_count = 0
    req_total_list = []
    req_pending_list = []
    req_approved_list = []
    req_completed_list = []
    
    is_fleet_staff = "fozone" in request.user.username or "Fleet" in request.user.username or "fleet" in request.user.username or request.user.username in ["Manager_Admin", "MngrFleet", "Fleet_Manager"]
    if is_fleet_staff:
        from .models import VehicleRequisition
        if request.user.username in ['Manager_Admin', 'Fleet_Manager', 'MngrFleet']:
            req_qs = VehicleRequisition.objects.all()
        else:
            req_qs = VehicleRequisition.objects.filter(fleet_officer=request.user)
            
        req_total_count = req_qs.count()
        req_pending_count = req_qs.filter(status='Pending').count()
        req_approved_count = req_qs.filter(status='Approved').count()
        req_completed_count = req_qs.filter(status='Completed').count()
        req_rejected_count = req_qs.filter(status='Rejected').count()
        
        req_total_list = req_qs.order_by('-created_at')
        req_pending_list = req_qs.filter(status='Pending').order_by('-created_at')
        req_approved_list = req_qs.filter(status='Approved').order_by('-created_at')
        req_completed_list = req_qs.filter(status='Completed').order_by('-created_at')

    context = {
        # Notesheets lists/counts
        "ns_total_count": ns_total_count,
        "ns_files_count": ns_files.count(),
        "ns_inbox_count": ns_inbox.count(),
        "ns_outbox_count": ns_outbox.count(),
        "ns_files_list": ns_files,
        "ns_inbox_list": ns_inbox,
        "ns_outbox_list": ns_outbox,
        "ns_category_labels": ns_category_labels,
        "ns_category_data": ns_category_data,

        # Tasks lists/counts
        "tasks_total_count": tasks_total.count(),
        "tasks_pending_count": tasks_pending.count(),
        "tasks_completed_count": tasks_completed.count(),
        "tasks_overdue_count": tasks_overdue.count(),
        "tasks_total_list": tasks_total,
        "tasks_pending_list": tasks_pending,
        "tasks_completed_list": tasks_completed,
        "tasks_overdue_list": tasks_overdue,
        "upcoming_tasks": upcoming_tasks,
        "task_category_labels": task_category_labels,
        "task_category_data": task_category_data,

        # Letters lists/counts
        "letters_total_count": letters_total_count,
        "letters_drafts_count": letters_drafts_count,
        "letters_outbox_count": letters_outbox_count,
        "letters_inbox_count": letters_inbox_count,
        "letters_total_list": letters_total,
        "letters_drafts_list": letters_drafts,
        "letters_outbox_list": letters_outbox,
        "letters_inbox_list": letters_inbox,
        "letter_category_labels": letter_category_labels,
        "letter_category_data": letter_category_data,

        # Requisitions (Fleet_Manager)
        "req_total_count": req_total_count,
        "req_pending_count": req_pending_count,
        "req_approved_count": req_approved_count,
        "req_completed_count": req_completed_count,
        "req_rejected_count": req_rejected_count,
        "req_total_list": req_total_list,
        "req_pending_list": req_pending_list,
        "req_approved_list": req_approved_list,
        "req_completed_list": req_completed_list,
    }
    
    return render(request, 'manager_dashboard.html', context)

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
import json
from datetime import datetime, timedelta

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.utils import timezone
from .models import Task, User # Jo bhi aapke models hain

@login_required
def gm_dashboard(request):
    from django.db.models import Q, Count
    from .models import Notesheet, NotesheetForward, File, Letter, Task, Commitment, Profile
    from django.utils import timezone
    from datetime import timedelta

    if hasattr(request.user, 'profile'):
        role = request.user.profile.role
        if role != 'GM':
            if role == 'CEO':
                return redirect('ceo_dashboard')
            elif role == 'PS':
                return redirect('ps_dashboard')
            else:
                return redirect('manager_dashboard')

    today = timezone.now()
    next_week = today + timedelta(days=7)

    # 1. Notesheets Data (My files, My inbox, My outbox)
    ns_files = File.objects.filter(created_by=request.user).order_by('-created_at')
    ns_inbox = Notesheet.objects.filter(current_holder=request.user).order_by('-updated_at')
    
    ns_forwarded_ids = NotesheetForward.objects.filter(forwarded_by=request.user).values_list('notesheet_id', flat=True)
    ns_outbox = Notesheet.objects.filter(
        Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).exclude(current_holder=request.user).distinct().order_by('-updated_at')

    ns_total_count = Notesheet.objects.filter(
        Q(current_holder=request.user) | Q(created_by=request.user) | Q(id__in=ns_forwarded_ids)
    ).distinct().count()

    ns_status_counts = {
        'Files': ns_files.count(),
        'Inbox': ns_inbox.count(),
        'Outbox': ns_outbox.count()
    }
    ns_category_labels = list(ns_status_counts.keys())
    ns_category_data = list(ns_status_counts.values())

    # 2. Tasks Data (Tasks assigned TO or BY the GM)
    my_tasks = Task.objects.filter(Q(assigned_to=request.user) | Q(assigned_by=request.user)).distinct()
    
    tasks_total = my_tasks.order_by('-created_at')
    tasks_pending = my_tasks.exclude(status='Completed').order_by('-created_at')
    tasks_completed = my_tasks.filter(status='Completed').order_by('-created_at')
    tasks_overdue = my_tasks.filter(due_date__lt=today.date()).exclude(status='Completed').order_by('-created_at')
    
    upcoming_tasks = my_tasks.filter(
        due_date__range=(today.date(), next_week.date())
    ).exclude(status='Completed').order_by('due_date')

    task_status_counts = my_tasks.values('status').annotate(count=Count('id'))
    task_category_labels = [item['status'] if item['status'] else 'Uncategorized' for item in task_status_counts]
    task_category_data = [item['count'] for item in task_status_counts]

    # 3. Letters Data (My letters)
    letters_inbox = Letter.objects.filter(receiver=request.user, is_draft=False).order_by('-created_at')
    letters_outbox = Letter.objects.filter(sender=request.user, is_draft=False).order_by('-created_at')
    letters_drafts = Letter.objects.filter(sender=request.user, is_draft=True).order_by('-created_at')
    
    letters_total = list(letters_inbox) + list(letters_outbox) + list(letters_drafts)
    
    letters_drafts_count = letters_drafts.count()
    letters_inbox_count = letters_inbox.count()
    letters_outbox_count = letters_outbox.count()
    letters_total_count = len(letters_total)

    letter_category_labels = ['Inbox', 'Outbox', 'Drafts']
    letter_category_data = [letters_inbox_count, letters_outbox_count, letters_drafts_count]

    context = {
        # Notesheets lists/counts
        "ns_total_count": ns_total_count,
        "ns_files_count": ns_files.count(),
        "ns_inbox_count": ns_inbox.count(),
        "ns_outbox_count": ns_outbox.count(),
        "ns_files_list": ns_files,
        "ns_inbox_list": ns_inbox,
        "ns_outbox_list": ns_outbox,
        "ns_category_labels": ns_category_labels,
        "ns_category_data": ns_category_data,

        # Tasks lists/counts
        "tasks_total_count": tasks_total.count(),
        "tasks_pending_count": tasks_pending.count(),
        "tasks_completed_count": tasks_completed.count(),
        "tasks_overdue_count": tasks_overdue.count(),
        "tasks_total_list": tasks_total,
        "tasks_pending_list": tasks_pending,
        "tasks_completed_list": tasks_completed,
        "tasks_overdue_list": tasks_overdue,
        "upcoming_tasks": upcoming_tasks,
        "task_category_labels": task_category_labels,
        "task_category_data": task_category_data,

        # Letters lists/counts
        "letters_total_count": letters_total_count,
        "letters_drafts_count": letters_drafts_count,
        "letters_outbox_count": letters_outbox_count,
        "letters_inbox_count": letters_inbox_count,
        "letters_total_list": letters_total,
        "letters_drafts_list": letters_drafts,
        "letters_outbox_list": letters_outbox,
        "letters_inbox_list": letters_inbox,
        "letter_category_labels": letter_category_labels,
        "letter_category_data": letter_category_data,
    }
    
    return render(request, 'gm_dashboard.html', context)



from django.http import JsonResponse
from datetime import datetime
from .models import Task # Ensure Task model is imported

@login_required
def gm_chart_data(request):
    """
    Ye function frontend (JavaScript) ko asli data supply karega.
    """
    # JavaScript se dates ki list aayegi: ?dates=2026-01-29,2026-01-30...
    dates_str = request.GET.get('dates', '')
    if not dates_str:
        return JsonResponse([], safe=False)

    dates_list = dates_str.split(',')
    data = []
    
    # Which field to use for counting: 'created_at' (assigned date) or 'due_date'
    by_field = request.GET.get('by', 'created_at')

    for d_str in dates_list:
        try:
            # String ko date object mein convert karna
            date_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
            
            # Asli Data: Check karein ke is din kitne tasks assign kiye is GM ne
            if by_field == 'due_date':
                # Count tasks whose due_date falls on this date
                count = Task.objects.filter(
                    due_date__date=date_obj,
                    assigned_by=request.user
                ).count()
            else:
                # Default: count by creation/assignment date
                count = Task.objects.filter(
                    created_at__date=date_obj,
                    assigned_by=request.user
                ).count()
            
            data.append(count)
        except (ValueError, TypeError):
            data.append(0)
    
    return JsonResponse(data, safe=False)


from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Task, Remark, TaskTracking, Profile, Notesheet, NotesheetForward, NotesheetAgenda, File
from .forms import InitiateNotesheetForm

# =========================================================
# 1. FILE MANAGEMENT VIEWS (STAGES 2 & 3)
# =========================================================

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import File  # Aapka File model

@login_required
def notesheet_files(request):
    files = File.objects.filter(created_by=request.user).order_by('-created_at')
    return render(request, 'notesheet_files.html', {'files': files})

@login_required
def create_file(request):
    """Nayi File/Folder banane ke liye"""
    if request.method == "POST":
        name = request.POST.get('file_name')
        number = request.POST.get('file_number')
        desc = request.POST.get('description')
        
        if number:
            number = number.strip()
        if not number:
            number = None
        
        if name:
            # Check if file_number already exists (if provided)
            if number and File.objects.filter(file_number=number).exists():
                messages.error(request, f"File number '{number}' already exists. Please use a different file number.")
            else:
                File.objects.create(
                    file_name=name,
                    file_number=number,
                    description=desc,
                    created_by=request.user
                )
                messages.success(request, f"File '{name}' created successfully!")
                return redirect('notesheet_files')
        else:
            messages.error(request, "Please fill the file name.")
            
    return render(request, 'create_file.html')

@login_required
def file_detail(request, file_id):
    file_obj = get_object_or_404(File, id=file_id)
    
    task_records = list(file_obj.tasks.all())
    notesheet_records = list(file_obj.notesheets.all())
    combined_records = sorted(
        task_records + notesheet_records,
        key=lambda item: item.created_at,
        reverse=True
    )

    return render(request, 'file_detail.html', {
        'file': file_obj,
        'tasks': combined_records
    })
# =========================================================
# 2. TASK / NOTESHEET SYSTEM 1 (Manager Logic)
# =========================================================

@login_required
@xframe_options_sameorigin
def initiate_notesheet(request):
    from .models import NotesheetAttachment, NotesheetAgenda

    file_id = request.GET.get('file_id')
    from django.db.models import Case, When, Value, IntegerField
    
    hierarchy = UserHierarchy.objects.filter(boss=request.user).first()
    if hierarchy and hierarchy.notesheet_subs.exists():
        base_qs = hierarchy.notesheet_subs.all()
    else:
        base_qs = User.objects.exclude(id=request.user.id)

    all_users = base_qs.annotate(
        role_order=Case(
            When(Q(profile__role__category='CEO') | Q(profile__role__code='CEO'), then=Value(1)),
            When(Q(profile__role__category='PS') | Q(profile__role__code='PS'), then=Value(2)),
            When(Q(profile__role__category='GM') | Q(profile__role__code='GM'), then=Value(3)),
            When(Q(profile__role__category='Manager') | Q(profile__role__code='Manager'), then=Value(4)),
            When(Q(profile__role__category='ZM') | Q(profile__role__code='ZM'), then=Value(5)),
            When(Q(profile__role__category='Field Manager') | Q(profile__role__code='Field Manager'), then=Value(6)),
            When(Q(profile__role__category='IT') | Q(profile__role__code='IT'), then=Value(7)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('role_order', 'username')

    if request.method == "POST":
        form = InitiateNotesheetForm(request.POST, request.FILES)
        agenda_titles = request.POST.getlist('agenda_title[]')
        post_file_id = request.POST.get('file_id')

        valid_file_id = None
        if post_file_id and post_file_id.isdigit():
            valid_file_id = int(post_file_id)
        elif file_id and str(file_id).isdigit():
            valid_file_id = int(file_id)

        if form.is_valid():
            notesheet = form.save(commit=False)
            target_user = form.cleaned_data.get('forward_to_user')

            if not target_user:
                form.add_error('forward_to_user', 'Please select a user.')
            else:
                notesheet.current_holder = target_user
                notesheet.created_by = request.user

                if valid_file_id is not None:
                    notesheet.file_id = valid_file_id

                notesheet.status = 'Pending'
                notesheet.save()

                for content in agenda_titles:
                    if content.strip():
                        NotesheetAgenda.objects.create(
                            notesheet=notesheet,
                            agenda_title=content.strip()
                        )

                uploaded_files = request.FILES.getlist('attachments') if request.FILES else []
                attachment_labels = request.POST.getlist('attachment_labels[]')

                for i, f in enumerate(uploaded_files):
                    label = attachment_labels[i] if i < len(attachment_labels) else None
                    NotesheetAttachment.objects.create(
                        notesheet=notesheet,
                        file=f,
                        flag_name=label
                    )

                attached_logbook_paths = request.POST.getlist('attached_logbook_paths[]')
                for path in attached_logbook_paths:
                    if path:
                        NotesheetAttachment.objects.create(
                            notesheet=notesheet,
                            file=path,
                            flag_name='LogBook'
                        )

                messages.success(request, f"Notesheet '{notesheet.title}' created successfully!")
                return redirect('notesheet_outbox')
        else:
            messages.error(request, "Please fix the errors below and resubmit.")

    else:
        form = InitiateNotesheetForm()

    return render(request, 'initiate_notesheet.html', {
        'form': form,
        'file_id': file_id,
        'users': all_users
    })

# =========================================================
# 3. OTHER VIEWS (VIEWING & FORWARDING)
# =========================================================

@login_required
def view_notesheet(request, task_id):
    from .models import NotesheetAttachment, NotesheetReturn  # ✅ NotesheetReturn ko bhi import kiya
    
    # First try Notesheet and then fall back to Task for backward compatibility
    notesheet = None
    is_task = False

    try:
        notesheet = Notesheet.objects.get(id=task_id)
    except Notesheet.DoesNotExist:
        try:
            notesheet = Task.objects.get(id=task_id)
            is_task = True
        except Task.DoesNotExist:
            messages.error(request, f"Notesheet with ID {task_id} not found.")
            return redirect('notesheet_files')

    if is_task:
        if notesheet.assigned_to == request.user and not notesheet.is_seen:
            notesheet.is_seen = True
            notesheet.seen_at = timezone.now()
            notesheet.save(update_fields=['is_seen', 'seen_at'])
        remarks = notesheet.remarks.all().order_by('created_at')
        agendas = []
        forwards = []
        attachments = []  # Tasks ke liye khali rkhlein
        returns = []      # Tasks ke liye returns bhi khali rhega
    else:
        if notesheet.current_holder == request.user and not notesheet.is_seen:
            notesheet.is_seen = True
            notesheet.seen_at = timezone.now()
            notesheet.save(update_fields=['is_seen', 'seen_at'])
        remarks = []
        agendas = notesheet.agendas.all()
        forwards = notesheet.forwards.all()
        
        # ✅ IMPORTANT: Is notesheet ki saari initial attachments fetch karli hain
        attachments = NotesheetAttachment.objects.filter(notesheet=notesheet)
        
        # ✅ NEW: Is notesheet ki saari return history aur manager ke remarks nikaal liye
        returns = NotesheetReturn.objects.filter(notesheet=notesheet).order_by('-returned_at')

    context = {
        'notesheet': notesheet,
        'remarks': remarks,
        'agendas': agendas,
        'forwards': forwards,
        'attachments': attachments,  # ✅ Context mein pass kardiya
        'return_history': returns,    # ✅ Return history ko template ke liye pass kardiya
    }
    return render(request, 'view_notesheet.html', context)

@login_required
def notesheet_detail(request, task_id):
    notesheet = get_object_or_404(Task, id=task_id)
    officers = User.objects.filter(profile__isnull=False).exclude(id=request.user.id).select_related('profile').order_by('username')

    if request.method == 'POST':
        feedback_text = request.POST.get('remarks')
        forward_to_id = request.POST.get('forward_to')

        if feedback_text:
            Remark.objects.create(task=notesheet, manager=request.user, feedback=feedback_text)
            if forward_to_id:
                new_officer = User.objects.get(id=forward_to_id)
                notesheet.assigned_to = new_officer
                notesheet.status = 'In Progress'
                notesheet.save()
            return redirect('view_notesheets')

    return render(request, 'notesheet_detail.html', {'notesheet': notesheet, 'officers': officers})

@login_required
def my_notesheets(request):
    task_notesheets = Task.objects.filter(assigned_to=request.user)
    notesheet_items = Notesheet.objects.filter(
        Q(current_holder=request.user) | Q(created_by=request.user)
    ).distinct()
    combined_notesheets = sorted(
        list(task_notesheets) + list(notesheet_items),
        key=lambda item: item.created_at,
        reverse=True
    )
    return render(request, "my_notesheets.html", {"notesheets": combined_notesheets}) 


@login_required
def forward_notesheet(request, pk):
    notesheet = None
    is_task = False

    try:
        notesheet = Notesheet.objects.get(pk=pk)
    except Notesheet.DoesNotExist:
        try:
            notesheet = Task.objects.get(pk=pk)
            is_task = True
        except Task.DoesNotExist:
            return HttpResponseNotFound("No notesheet found with that ID.")

    if is_task:
        if notesheet.assigned_to != request.user and notesheet.assigned_by != request.user:
            messages.error(request, "You are not allowed to forward this.")
            return redirect('notesheet_outbox')
    else:
        if notesheet.current_holder != request.user and notesheet.created_by != request.user:
            messages.error(request, "You are not allowed to forward this.")
            return redirect('notesheet_outbox')
# 2. TASK / NOTESHEET SYSTEM 1 (Manager Logic)
# =========================================================

@login_required
@xframe_options_sameorigin
def initiate_notesheet(request):
    from .models import NotesheetAttachment, NotesheetAgenda

    file_id = request.GET.get('file_id')
    from django.db.models import Case, When, Value, IntegerField
    all_users = User.objects.exclude(id=request.user.id).annotate(
        role_order=Case(
            When(Q(profile__role__category='CEO') | Q(profile__role__code='CEO'), then=Value(1)),
            When(Q(profile__role__category='PS') | Q(profile__role__code='PS'), then=Value(2)),
            When(Q(profile__role__category='GM') | Q(profile__role__code='GM'), then=Value(3)),
            When(Q(profile__role__category='Manager') | Q(profile__role__code='Manager'), then=Value(4)),
            When(Q(profile__role__category='ZM') | Q(profile__role__code='ZM'), then=Value(5)),
            When(Q(profile__role__category='Field Manager') | Q(profile__role__code='Field Manager'), then=Value(6)),
            When(Q(profile__role__category='IT') | Q(profile__role__code='IT'), then=Value(7)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('role_order', 'username')

    if request.method == "POST":
        form = InitiateNotesheetForm(request.POST, request.FILES)
        agenda_titles = request.POST.getlist('agenda_title[]')
        post_file_id = request.POST.get('file_id')

        valid_file_id = None
        if post_file_id and post_file_id.isdigit():
            valid_file_id = int(post_file_id)
        elif file_id and str(file_id).isdigit():
            valid_file_id = int(file_id)

        if form.is_valid():
            notesheet = form.save(commit=False)
            target_user = form.cleaned_data.get('forward_to_user')

            if not target_user:
                form.add_error('forward_to_user', 'Please select a user.')
            else:
                notesheet.current_holder = target_user
                notesheet.created_by = request.user

                if valid_file_id is not None:
                    notesheet.file_id = valid_file_id

                notesheet.status = 'Pending'
                notesheet.save()

                for content in agenda_titles:
                    if content.strip():
                        NotesheetAgenda.objects.create(
                            notesheet=notesheet,
                            agenda_title=content.strip()
                        )

                uploaded_files = request.FILES.getlist('attachments') if request.FILES else []
                attachment_labels = request.POST.getlist('attachment_labels[]')

                for i, f in enumerate(uploaded_files):
                    label = attachment_labels[i] if i < len(attachment_labels) else None
                    NotesheetAttachment.objects.create(
                        notesheet=notesheet,
                        file=f,
                        flag_name=label
                    )

                attached_logbook_paths = request.POST.getlist('attached_logbook_paths[]')
                for path in attached_logbook_paths:
                    if path:
                        NotesheetAttachment.objects.create(
                            notesheet=notesheet,
                            file=path,
                            flag_name='LogBook'
                        )

                create_notification(
                    recipient=target_user,
                    sender=request.user,
                    title=f"New Notesheet Received",
                    message=f"Notesheet '{notesheet.title}' has been initiated by {request.user.username}.",
                    link=f"/notesheet/view/{notesheet.id}/",
                    notification_type='notesheet'
                )
                # Sender confirmation notification
                create_notification(
                    recipient=request.user,
                    sender=request.user,
                    title=f"You have sent notesheet '{notesheet.title}' to {target_user.username}.",
                    message="",
                    link=f"/notesheet/view/{notesheet.id}/",
                    notification_type='notesheet',
                    allow_self=True
                )

                messages.success(request, f"Notesheet '{notesheet.title}' created successfully!")
                return redirect('notesheet_outbox')
        else:
            messages.error(request, "Please fix the errors below and resubmit.")

    else:
        form = InitiateNotesheetForm()

    files = File.objects.filter(created_by=request.user).order_by('-created_at')

    return render(request, 'initiate_notesheet.html', {
        'form': form,
        'file_id': file_id,
        'users': all_users,
        'files': files
    })

# =========================================================
# 3. OTHER VIEWS (VIEWING & FORWARDING)
# =========================================================

@login_required
def view_notesheet(request, task_id):
    from .models import NotesheetAttachment, NotesheetReturn  # ✅ NotesheetReturn ko bhi import kiya
    
    # First try Notesheet and then fall back to Task for backward compatibility
    notesheet = None
    is_task = False

    try:
        notesheet = Notesheet.objects.get(id=task_id)
    except Notesheet.DoesNotExist:
        try:
            notesheet = Task.objects.get(id=task_id)
            is_task = True
        except Task.DoesNotExist:
            messages.error(request, f"Notesheet with ID {task_id} not found.")
            return redirect('notesheet_files')

    if is_task:
        if notesheet.assigned_to == request.user and not notesheet.is_seen:
            notesheet.is_seen = True
            notesheet.seen_at = timezone.now()
            notesheet.save(update_fields=['is_seen', 'seen_at'])
        remarks = notesheet.remarks.all().order_by('created_at')
        agendas = []
        forwards = []
        attachments = []  # Tasks ke liye khali rkhlein
        returns = []      # Tasks ke liye returns bhi khali rhega
    else:
        if notesheet.current_holder == request.user and not notesheet.is_seen:
            notesheet.is_seen = True
            notesheet.seen_at = timezone.now()
            notesheet.save(update_fields=['is_seen', 'seen_at'])
        remarks = []
        agendas = notesheet.agendas.all()
        forwards = notesheet.forwards.all()
        
        # ✅ IMPORTANT: Is notesheet ki saari initial attachments fetch karli hain
        attachments = NotesheetAttachment.objects.filter(notesheet=notesheet)
        
        # ✅ NEW: Is notesheet ki saari return history aur manager ke remarks nikaal liye
        returns = NotesheetReturn.objects.filter(notesheet=notesheet).order_by('-returned_at')

    context = {
        'notesheet': notesheet,
        'remarks': remarks,
        'agendas': agendas,
        'forwards': forwards,
        'attachments': attachments,  # ✅ Context mein pass kardiya
        'return_history': returns,    # ✅ Return history ko template ke liye pass kardiya
    }
    return render(request, 'view_notesheet.html', context)

@login_required
def notesheet_detail(request, task_id):
    notesheet = get_object_or_404(Task, id=task_id)
    officers = User.objects.filter(profile__isnull=False).exclude(id=request.user.id).select_related('profile').order_by('username')

    if request.method == 'POST':
        feedback_text = request.POST.get('remarks')
        forward_to_id = request.POST.get('forward_to')

        if feedback_text:
            Remark.objects.create(task=notesheet, manager=request.user, feedback=feedback_text)
            if forward_to_id:
                new_officer = User.objects.get(id=forward_to_id)
                notesheet.assigned_to = new_officer
                notesheet.status = 'In Progress'
                notesheet.save()
            return redirect('view_notesheets')

    return render(request, 'notesheet_detail.html', {'notesheet': notesheet, 'officers': officers})

@login_required
def my_notesheets(request):
    task_notesheets = Task.objects.filter(assigned_to=request.user)
    notesheet_items = Notesheet.objects.filter(
        Q(current_holder=request.user) | Q(created_by=request.user)
    ).distinct()
    combined_notesheets = sorted(
        list(task_notesheets) + list(notesheet_items),
        key=lambda item: item.created_at,
        reverse=True
    )
    return render(request, "my_notesheets.html", {"notesheets": combined_notesheets}) 

import re
def get_next_para_num(notesheet, is_task=False):
    count = 0
    if not is_task:
        for agenda in notesheet.agendas.all():
            content = agenda.agenda_title or ''
            lis = re.findall(r'<li[^>]*>', content, re.IGNORECASE)
            if lis: count += len(lis)
            else:
                ps = re.findall(r'<p[^>]*>', content, re.IGNORECASE)
                count += len(ps) if ps else 1
        for forward in notesheet.forwards.all():
            content = forward.remark or ''
            lis = re.findall(r'<li[^>]*>', content, re.IGNORECASE)
            if lis: count += len(lis)
            else:
                ps = re.findall(r'<p[^>]*>', content, re.IGNORECASE)
                count += len(ps) if ps else 1
        for ret in notesheet.returns.all():
            content = ret.remark or ''
            lis = re.findall(r'<li[^>]*>', content, re.IGNORECASE)
            if lis: count += len(lis)
            else:
                ps = re.findall(r'<p[^>]*>', content, re.IGNORECASE)
                count += len(ps) if ps else 1
    else:
        for remark in notesheet.remarks.all():
            content = remark.feedback or ''
            lis = re.findall(r'<li[^>]*>', content, re.IGNORECASE)
            if lis: count += len(lis)
            else:
                ps = re.findall(r'<p[^>]*>', content, re.IGNORECASE)
                count += len(ps) if ps else 1
    return count + 1


@login_required
def forward_notesheet(request, pk):
    notesheet = None
    is_task = False

    try:
        notesheet = Notesheet.objects.get(pk=pk)
    except Notesheet.DoesNotExist:
        try:
            notesheet = Task.objects.get(pk=pk)
            is_task = True
        except Task.DoesNotExist:
            return HttpResponseNotFound("No notesheet found with that ID.")

    if is_task:
        if notesheet.assigned_to != request.user and notesheet.assigned_by != request.user:
            messages.error(request, "You are not allowed to forward this.")
            return redirect('notesheet_outbox')
    else:
        if notesheet.current_holder != request.user and notesheet.created_by != request.user:
            messages.error(request, "You are not allowed to forward this.")
            return redirect('notesheet_outbox')

    if request.method == "POST":
        forwarded_to_id = request.POST.get("forwarded_to")
        remark_text = request.POST.get("remark")

        try:
            forwarded_user = User.objects.get(id=forwarded_to_id)
            if not is_task:
                forward_obj = NotesheetForward.objects.create(
                    notesheet=notesheet,
                    forwarded_by=request.user,
                    forwarded_to=forwarded_user,
                    remark=remark_text,
                )

                # Attachments with labels save karo
                uploaded_files = request.FILES.getlist('attachments')
                
                # Assign up to 3 attachments directly to the forward object
                for i, f in enumerate(uploaded_files[:3]):
                    if f:
                        if i == 0:
                            forward_obj.attachment_1 = f
                        elif i == 1:
                            forward_obj.attachment_2 = f
                        elif i == 2:
                            forward_obj.attachment_3 = f
                forward_obj.save()

                attachment_labels = request.POST.getlist('attachment_labels[]')
                for i, f in enumerate(uploaded_files):
                    if f:
                        label = attachment_labels[i] if i < len(attachment_labels) else None
                        NotesheetAttachment.objects.create(
                            notesheet=notesheet,
                            file=f,
                            flag_name=label,
                        )
            else:
                TaskTracking.objects.create(
                    task=notesheet,
                    from_user=request.user,
                    to_user=forwarded_user,
                    message=f"Forwarded notesheet with remark: {remark_text or 'No remark'}"
                )

            if is_task:
                notesheet.assigned_to = forwarded_user
            else:
                notesheet.current_holder = forwarded_user

            notesheet.is_seen = False
            notesheet.seen_at = None
            notesheet.status = "In Progress"
            notesheet.save()

            create_notification(
                recipient=forwarded_user,
                sender=request.user,
                title=f"{'Task' if is_task else 'Notesheet'} Received",
                message=f"'{notesheet.title}' has been forwarded to you by {request.user.username}.",
                link=f"/notesheet/view/{notesheet.id}/" if not is_task else "/manager/tasks/",
                notification_type='task' if is_task else 'notesheet'
            )
            # Sender confirmation notification
            create_notification(
                recipient=request.user,
                sender=request.user,
                title=f"You have forwarded '{notesheet.title}' to {forwarded_user.username}.",
                message="",
                link=f"/notesheet/view/{notesheet.id}/" if not is_task else "/manager/tasks/",
                notification_type='task' if is_task else 'notesheet',
                allow_self=True
            )

            messages.success(request, f"Forwarded to {forwarded_user.username}.")
            return redirect('notesheet_outbox')
        except User.DoesNotExist:
            messages.error(request, "Officer not found.")

    # ── GET: existing flags/annexure/puc count SEPARATELY calculate karo ──
    existing_flag_count = 0
    existing_annexure_count = 0
    existing_puc_count = 0

    if not is_task:
        all_attachments = NotesheetAttachment.objects.filter(notesheet=notesheet)
        for att in all_attachments:
            name = (att.flag_name or '').strip()
            if name.startswith('Flag'):
                existing_flag_count += 1
            elif name.startswith('Annexure'):
                existing_annexure_count += 1
            elif name.startswith('PUC'):
                existing_puc_count += 1
            else:
                existing_flag_count += 1

    from django.db.models import Case, When, Value, IntegerField
    
    hierarchy = UserHierarchy.objects.filter(boss=request.user).first()
    if hierarchy and hierarchy.notesheet_subs.exists():
        base_qs = hierarchy.notesheet_subs.all()
    else:
        base_qs = User.objects.exclude(id=request.user.id)

    users = base_qs.annotate(
        role_order=Case(
            When(Q(profile__role__category='CEO') | Q(profile__role__code='CEO'), then=Value(1)),
            When(Q(profile__role__category='PS') | Q(profile__role__code='PS'), then=Value(2)),
            When(Q(profile__role__category='GM') | Q(profile__role__code='GM'), then=Value(3)),
            When(Q(profile__role__category='Manager') | Q(profile__role__code='Manager'), then=Value(4)),
            When(Q(profile__role__category='ZM') | Q(profile__role__code='ZM'), then=Value(5)),
            When(Q(profile__role__category='Field Manager') | Q(profile__role__code='Field Manager'), then=Value(6)),
            When(Q(profile__role__category='IT') | Q(profile__role__code='IT'), then=Value(7)),
            default=Value(99),
            output_field=IntegerField(),
        )
    ).order_by('role_order', 'username')
    
    next_para_num = get_next_para_num(notesheet, is_task)

    return render(request, "forward_notesheet.html", {
        "notesheet": notesheet,
        "users": users,
        "existing_flag_count": existing_flag_count,
        "existing_annexure_count": existing_annexure_count,
        "existing_puc_count": existing_puc_count,
        "next_para_num": next_para_num,
    })


# =========================================================
# 3. OTHER VIEWS (VIEWING & FORWARDING)
# =========================================================

@login_required
def view_notesheet(request, task_id):
    from .models import NotesheetAttachment, NotesheetReturn
    import re
    
    def extract_letterhead(text):
        """Extracts letterhead from text and returns (letterhead, clean_text)"""
        if not text:
            return '', ''
            
        letterhead = ''
        clean_text = text
        
        # Check for new letterhead div format (mceNonEditable)
        match = re.search(r'(<div class="mceNonEditable"[^>]*>.*?</div>\s*(?:<hr[^>]*>|<div[^>]*border-top[^>]*></div>))', text, re.IGNORECASE | re.DOTALL)
        if match:
            letterhead = match.group(1)
            clean_text = text[match.end():]
        else:
            # Fallback for old letterhead format
            if 'CHIEF EXECUTIVE OFFICER' in text and ('091-9219018' in text or '091-9219074' in text):
                match = re.search(r'(<table.*?</table>\s*(?:<div[^>]*></div>|<hr[^>]*>)?)', text, re.IGNORECASE | re.DOTALL)
                if match:
                    letterhead = match.group(1)
                    clean_text = text[match.end():]
                    
        # Clean up any leading empty p tags or brs
        clean_text = re.sub(r'^\s*(<p>&nbsp;</p>|<p>\s*</p>|<br\s*/?>)\s*', '', clean_text, count=1, flags=re.IGNORECASE).strip()
        
        return letterhead, clean_text
    
    # First try Notesheet and then fall back to Task for backward compatibility
    notesheet = None
    is_task = False

    try:
        notesheet = Notesheet.objects.get(id=task_id)
    except Notesheet.DoesNotExist:
        try:
            notesheet = Task.objects.get(id=task_id)
            is_task = True
        except Task.DoesNotExist:
            messages.error(request, f"Notesheet with ID {task_id} not found.")
            return redirect('notesheet_files')

    if is_task:
        if notesheet.assigned_to == request.user and not notesheet.is_seen:
            notesheet.is_seen = True
            notesheet.seen_at = timezone.now()
            notesheet.save(update_fields=['is_seen', 'seen_at'])
            # Update existing sent notification instead of creating a new one
            sender_user = notesheet.assigned_by
            if sender_user and sender_user != request.user:
                sent_notification = Notification.objects.filter(
                    recipient=sender_user,
                    link=f"/notesheet/view/{notesheet.id}/"
                ).filter(
                    Q(title__icontains="sent") | Q(title__icontains="forwarded") | Q(title__icontains="returned")
                ).order_by('-created_at').first()

                if sent_notification:
                    seen_time = timezone.localtime(timezone.now()).strftime("%d %b, %I:%M %p")
                    seen_badge = f"<div style='margin-top: 6px; display: inline-flex; align-items: center; gap: 4px; background: #ecfdf5; color: #059669; padding: 2px 8px; border-radius: 12px; font-weight: 500; font-size: 0.7rem;'><i class='fas fa-check-double'></i> Seen at {seen_time}</div>"
                    sent_notification.message = seen_badge
                    sent_notification.is_read = False
                    sent_notification.created_at = timezone.now()
                    sent_notification.save()
        remarks = notesheet.remarks.all().order_by('created_at')
        agendas = []
        forwards = []
        attachments = []
        returns = []
    else:
        if notesheet.current_holder == request.user and not notesheet.is_seen:
            notesheet.is_seen = True
            notesheet.seen_at = timezone.now()
            notesheet.save(update_fields=['is_seen', 'seen_at'])
            # Update existing sent notification instead of creating a new one
            last_forward = notesheet.forwards.order_by('-forwarded_at').first()
            if last_forward:
                sender_user = last_forward.forwarded_by
            else:
                sender_user = notesheet.created_by
            if sender_user and sender_user != request.user:
                sent_notification = Notification.objects.filter(
                    recipient=sender_user,
                    link=f"/notesheet/view/{notesheet.id}/"
                ).filter(
                    Q(title__icontains="sent") | Q(title__icontains="forwarded") | Q(title__icontains="returned")
                ).order_by('-created_at').first()

                if sent_notification:
                    seen_time = timezone.localtime(timezone.now()).strftime("%d %b, %I:%M %p")
                    seen_badge = f"<div style='margin-top: 6px; display: inline-flex; align-items: center; gap: 4px; background: #ecfdf5; color: #059669; padding: 2px 8px; border-radius: 12px; font-weight: 500; font-size: 0.7rem;'><i class='fas fa-check-double'></i> Seen at {seen_time}</div>"
                    sent_notification.message = seen_badge
                    sent_notification.is_read = False
                    sent_notification.created_at = timezone.now()
                    sent_notification.save()
        remarks = []
        
        clean_agendas = []
        for agenda in notesheet.agendas.all():
            lh, content = extract_letterhead(agenda.agenda_title)
            clean_agendas.append({
                'obj': agenda,
                'letterhead': lh,
                'content': content
            })
        forwards = notesheet.forwards.all().order_by('forwarded_at')
        
        attachments = NotesheetAttachment.objects.filter(notesheet=notesheet)
        returns = NotesheetReturn.objects.filter(notesheet=notesheet).order_by('returned_at')

    all_attachments = list(attachments) if not is_task else []
    used_att_ids = set()

    # Build clean_forwards with HTML-stripped remarks and matched attachments for template
    clean_forwards = []
    for fwd in forwards:
        fwd_atts = []
        # Match attachments uploaded within 15 seconds of this forward
        matched = [a for a in all_attachments if abs((a.uploaded_at - fwd.forwarded_at).total_seconds()) < 15 and a.id not in used_att_ids]
        matched.sort(key=lambda x: x.id)
        for a in matched:
            used_att_ids.add(a.id)
            fwd_atts.append(a)
            
        lh, content = extract_letterhead(fwd.remark)
        clean_forwards.append({
            'type': 'forward',
            'action_date': fwd.forwarded_at,
            'actor': fwd.forwarded_by,
            'receiver': fwd.forwarded_to,
            'obj': fwd,
            'letterhead': lh,
            'clean_remark': content,
            'rich_attachments': fwd_atts,
        })
    
    # Build clean_returns with HTML-stripped remarks and matched attachments for template
    clean_returns = []
    for ret in returns:
        ret_atts = []
        # Match attachments uploaded within 15 seconds of this return
        matched = [a for a in all_attachments if abs((a.uploaded_at - ret.returned_at).total_seconds()) < 15 and a.id not in used_att_ids]
        matched.sort(key=lambda x: x.id)
        for a in matched:
            used_att_ids.add(a.id)
            ret_atts.append(a)
            
        lh, content = extract_letterhead(ret.remark)
        clean_returns.append({
            'type': 'return',
            'action_date': ret.returned_at,
            'actor': ret.returned_by,
            'receiver': ret.returned_to,
            'obj': ret,
            'letterhead': lh,
            'clean_remark': content,
            'rich_attachments': ret_atts,
        })
        
    initial_attachments = [a for a in all_attachments if a.id not in used_att_ids]

    # Combine forwards and returns into a single unified timeline
    timeline = clean_forwards + clean_returns
    timeline.sort(key=lambda x: x['action_date'])

    initial_receiver = timeline[0]['actor'] if timeline else notesheet.current_holder

    context = {
        'notesheet': notesheet,
        'initial_receiver': initial_receiver,
        'remarks': remarks,
        'agendas': clean_agendas,
        'forwards': forwards,
        'clean_forwards': clean_forwards,
        'attachments': attachments,
        'initial_attachments': initial_attachments,
        'all_attachments': all_attachments,
        'return_history': returns,
        'clean_returns': clean_returns,
        'timeline': timeline,
    }
    return render(request, 'view_notesheet.html', context)


from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Notesheet, NotesheetForward, NotesheetReturn, NotesheetAttachment

@login_required
def return_notesheet(request, pk):
    # 1. Database se notesheet get karein
    notesheet = get_object_or_404(Notesheet, pk=pk)
    
    if request.method == 'POST':
        remark = request.POST.get('remark')
        current_user = request.user

        # ── Attachments + Flags dynamic handle ──
        attachments = request.FILES.getlist('attachments')

        # 2. History check karein (Forward aur Return dono tables mein)
        last_forward = NotesheetForward.objects.filter(notesheet=notesheet).order_by('-forwarded_at').first()
        last_return  = NotesheetReturn.objects.filter(notesheet=notesheet).order_by('-returned_at').first()
        
        target_user = None

        # 3. Agar dono history majood hain, toh check karo latest kaunsi hai
        if last_forward and last_return:
            if last_forward.forwarded_at > last_return.returned_at:
                if last_forward.forwarded_by != current_user:
                    target_user = last_forward.forwarded_by
            else:
                if last_return.returned_by != current_user:
                    target_user = last_return.returned_by
                    
        elif last_forward and last_forward.forwarded_by != current_user:
            target_user = last_forward.forwarded_by
            
        elif last_return and last_return.returned_by != current_user:
            target_user = last_return.returned_by

        # 4. CRITICAL FALLBACK
        if not target_user:
            if notesheet.created_by and notesheet.created_by != current_user:
                target_user = notesheet.created_by

        # 5. Data update aur save karein
        if target_user:
            notesheet.current_holder = target_user
            notesheet.status = 'Returned'
            notesheet.is_seen = False
            notesheet.save()
            
            # Return history save karein
            return_obj = NotesheetReturn.objects.create(
                notesheet=notesheet,
                returned_by=current_user,
                returned_to=target_user,
                remark=remark if remark else "Notesheet returned for corrections.",
            )

            # Assign up to 3 attachments directly to the return object
            for i, f in enumerate(attachments[:3]):
                if f:
                    if i == 0:
                        return_obj.attachment_1 = f
                    elif i == 1:
                        return_obj.attachment_2 = f
                    elif i == 2:
                        return_obj.attachment_3 = f
            return_obj.save()

            # ── Dynamic label attachments save karein ──
            attachment_labels = request.POST.getlist('attachment_labels[]')
            for i, file in enumerate(attachments):
                if file:
                    label = attachment_labels[i] if i < len(attachment_labels) else None
                    NotesheetAttachment.objects.create(
                        notesheet=notesheet,
                        file=file,
                        flag_name=label,
                    )

            create_notification(
                recipient=target_user,
                sender=current_user,
                title=f"Notesheet Returned",
                message=f"'{notesheet.title}' has been returned to you by {current_user.username}.",
                link=f"/notesheet/view/{notesheet.id}/",
                notification_type='notesheet'
            )
            # Sender confirmation notification
            create_notification(
                recipient=current_user,
                sender=current_user,
                title=f"You have returned '{notesheet.title}' to {target_user.username}.",
                message="",
                link=f"/notesheet/view/{notesheet.id}/",
                notification_type='notesheet',
                allow_self=True
            )

            messages.success(request, f"Notesheet returned successfully to {target_user.username}.")
        else:
            messages.error(request, "Cannot return this notesheet. No previous owner or creator found to return to.")

        # Role ke mutabiq sahi dashboard par redirect karein
        if request.user.profile.role == 'CEO':
            return redirect('ceo_dashboard')
        elif request.user.profile.role == 'GM':
            return redirect('gm_dashboard')
        elif request.user.profile.role in ['Manager', 'ZM', 'IT', 'IT Officer', 'CFO', 'HR', 'Auditor']:
            return redirect('manager_dashboard')
        elif request.user.profile.role == 'PS':
            return redirect('ps_dashboard')
        else:
            return redirect('notesheet_outbox')

    # ── GET: existing flags/annexure/puc count SEPARATELY calculate karo ──
    all_attachments = NotesheetAttachment.objects.filter(notesheet=notesheet)
    existing_flag_count = 0
    existing_annexure_count = 0
    existing_puc_count = 0
    for att in all_attachments:
        name = (att.flag_name or '').strip()
        if name.startswith('Flag'):
            existing_flag_count += 1
        elif name.startswith('Annexure'):
            existing_annexure_count += 1
        elif name.startswith('PUC'):
            existing_puc_count += 1
        else:
            # Unknown type — count as flag for safety
            existing_flag_count += 1

    next_para_num = get_next_para_num(notesheet)

    return render(request, 'return_notesheet.html', {
        'notesheet': notesheet,
        'existing_flag_count': existing_flag_count,
        'existing_annexure_count': existing_annexure_count,
        'existing_puc_count': existing_puc_count,
        'next_para_num': next_para_num,
    })





from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import LetterFile, Letter
from django.contrib.auth.models import User

# 1. Letter Files List Page View
@login_required
def letter_files_list(request):
    files = LetterFile.objects.filter(created_by=request.user)
    return render(request, 'letter_files.html', {'files': files})

# 2. Create New Letter File
@login_required
def create_letter_file(request):
    if request.method == 'POST':
        title = request.POST.get('file_title')
        ref_num = request.POST.get('reference_number')
        desc = request.POST.get('description')
        
        LetterFile.objects.create(
            file_title=title,
            reference_number=ref_num,
            description=desc,
            created_by=request.user
        )
        messages.success(request, "Letter File successfuly create ho gayi hai!")
        return redirect('letter_files_list')
        
    return render(request, 'create_letter_file.html')

# 3. New Letter Send View
@login_required
def create_letter(request):
    files = LetterFile.objects.filter(created_by=request.user)
    
    hierarchy = UserHierarchy.objects.filter(boss=request.user).first()
    if hierarchy and hierarchy.letter_subs.exists():
        users = hierarchy.letter_subs.all()
    else:
        users = User.objects.exclude(id=request.user.id)

    if request.method == 'POST':
        file_id = request.POST.get('letter_file', '').strip()
        receiver_id = request.POST.get('receiver', '').strip()
        subject = request.POST.get('subject', '').strip()
        body = request.POST.get('body', '')
        attachment = request.FILES.get('attachment')
        save_as_draft = request.POST.get('save_as_draft') == '1'

        # Validate letter file
        if not file_id:
            messages.error(request, "Please select a Letter File before continuing.")
            return render(request, 'create_letter.html', {'files': files, 'users': users})

        letter_file = get_object_or_404(LetterFile, id=file_id)

        if save_as_draft:
            # Receiver is optional for drafts
            if receiver_id:
                receiver = get_object_or_404(User, id=receiver_id)
            else:
                receiver = request.user  # placeholder for draft

            Letter.objects.create(
                letter_file=letter_file,
                sender=request.user,
                receiver=receiver,
                ref_no=request.POST.get('ref_no', ''),
                recipient_address=request.POST.get('recipient_address', ''),
                subject=subject or '(Draft)',
                body=body or '',
                signer_name=request.POST.get('signer_name', ''),
                signer_designation=request.POST.get('signer_designation', ''),
                cc_list=request.POST.get('cc_list', ''),
                attachment=attachment,
                is_draft=True
            )
            messages.success(request, "Letter draft save ho gai hai!")
            return redirect('letter_drafts')
        else:
            # Sending requires a recipient
            if not receiver_id:
                messages.error(request, "Letter issue karne ke liye recipient (Send To) select karna zaroori hai.")
                return render(request, 'create_letter.html', {'files': files, 'users': users})

            receiver = get_object_or_404(User, id=receiver_id)
            Letter.objects.create(
                letter_file=letter_file,
                sender=request.user,
                receiver=receiver,
                ref_no=request.POST.get('ref_no', ''),
                recipient_address=request.POST.get('recipient_address', ''),
                subject=subject,
                body=body,
                signer_name=request.POST.get('signer_name', ''),
                signer_designation=request.POST.get('signer_designation', ''),
                cc_list=request.POST.get('cc_list', ''),
                attachment=attachment,
                is_draft=False
            )
            
            create_notification(
                recipient=receiver,
                sender=request.user,
                title="New Letter Received",
                message=f"You have received a new letter: '{subject}'",
                link=f"/letters/detail/{Letter.objects.last().id}/",
                notification_type='letter'
            )
            
            messages.success(request, "Letter kamyabi se bhej diya gaya hai!")
            return redirect('letter_outbox')

    return render(request, 'create_letter.html', {'files': files, 'users': users})


# Draft Letters View
@login_required
def letter_drafts(request):
    search_query = request.GET.get('search', '')
    drafts = Letter.objects.filter(sender=request.user, is_draft=True)
    if search_query:
        from django.db.models import Q
        drafts = drafts.filter(
            Q(subject__icontains=search_query) |
            Q(ref_no__icontains=search_query) |
            Q(body__icontains=search_query)
        )
    return render(request, 'letter_drafts.html', {'drafts': drafts, 'search_query': search_query})

@login_required
def send_draft_letter(request, letter_id):
    letter = get_object_or_404(Letter, id=letter_id, sender=request.user, is_draft=True)
    if request.method == "POST":
        receiver_id = request.POST.get('receiver')
        if not receiver_id:
            messages.error(request, "Please select a system recipient before issuing the letter.")
            return redirect('letter_detail', letter_id=letter.id)
            
        receiver = get_object_or_404(User, id=receiver_id)
        letter.receiver = receiver
        letter.is_draft = False
        letter.save()

        create_notification(
            recipient=receiver,
            sender=request.user,
            title="New Letter Received",
            message=f"You have received a new letter: '{letter.subject}' by {request.user.username}",
            link=f"/letters/detail/{letter.id}/",
            notification_type='letter'
        )

        messages.success(request, f"Letter '{letter.subject}' issued successfully to {receiver.username}!")
        return redirect('letter_outbox')

    return redirect('letter_detail', letter_id=letter.id)


# 4. Inbox View (Mili hui Letters)
@login_required
def letter_inbox(request):
    search_query = request.GET.get('search', '')
    letters = Letter.objects.filter(receiver=request.user, is_draft=False)
    if search_query:
        from django.db.models import Q
        letters = letters.filter(
            Q(subject__icontains=search_query) |
            Q(ref_no__icontains=search_query) |
            Q(body__icontains=search_query) |
            Q(sender__username__icontains=search_query)
        )
    return render(request, 'letter_inbox.html', {'letters': letters, 'search_query': search_query})

# 5. Outbox View (Bheji hui Letters)
@login_required
def letter_outbox(request):
    search_query = request.GET.get('search', '')
    letters = Letter.objects.filter(sender=request.user, is_draft=False)
    if search_query:
        from django.db.models import Q
        letters = letters.filter(
            Q(subject__icontains=search_query) |
            Q(ref_no__icontains=search_query) |
            Q(body__icontains=search_query) |
            Q(receiver__username__icontains=search_query)
        )
    return render(request, 'letter_outbox.html', {'letters': letters, 'search_query': search_query})

# 6. Letter Detail Page View
@login_required
def letter_detail(request, letter_id):
    letter = get_object_or_404(Letter, id=letter_id)
    if letter.sender != request.user and letter.receiver != request.user:
        messages.error(request, "Aapko yeh letter dekhne ki ijazat nahi hai!")
        return redirect('letter_inbox')
    
    if letter.receiver == request.user and not letter.is_read:
        letter.is_read = True
        letter.save()
        
    users = User.objects.exclude(id=request.user.id) if letter.is_draft else None

    return render(request, 'letter_detail.html', {'letter': letter, 'users': users})


import base64
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Profile  # Apne Profile model ko import karein

@login_required
@xframe_options_sameorigin
def edit_profile_signature(request):
    # Safely profile instance get ya create karein
    profile, created = Profile.objects.get_or_create(user=request.user)

    # Where to go after saving — read from GET or POST
    next_param = request.GET.get('next') or request.POST.get('next', '')
    # Build the redirect URL safely
    if next_param.startswith('/'):
        next_url = next_param
        next_name = next_param.strip('/').replace('/', ' › ').title() or 'Back'
    else:
        try:
            from django.urls import reverse, NoReverseMatch
            next_url = reverse(next_param) if next_param else None
            next_name = next_param.replace('_', ' ').title() if next_param else 'Dashboard'
        except Exception:
            next_url = None
            next_name = 'Dashboard'

    if request.method == 'POST':
        signature_data = request.POST.get('signature_data', '').strip()
        signature_file = request.FILES.get('signature_file')

        # ── PRIORITY 1: Uploaded Image File ──
        if signature_file:
            profile.signature = signature_file
            profile.save()
            messages.success(request, "Signature image successfully uploaded and saved!")
            return redirect(next_url or 'edit_profile_signature')

        # ── PRIORITY 2: Drawn Base64 Signature ──
        elif signature_data and signature_data.startswith('data:image'):
            try:
                fmt, imgstr = signature_data.split(';base64,')
                ext = 'png' if 'png' in fmt else 'jpg'
                
                # Base64 string ko decode karke ContentFile banana
                file_obj = ContentFile(
                    base64.b64decode(imgstr),
                    name=f"signature_user_{request.user.id}.{ext}"
                )
                
                # ImageField par directly save karein taake storage override ho sake
                profile.signature.save(f"sig_user_{request.user.id}.{ext}", file_obj, save=True)
                
                messages.success(request, "Digital signature successfully saved!")
                return redirect(next_url or 'edit_profile_signature')
            except Exception as e:
                messages.error(request, f"Error processing signature: {str(e)}")

        else:
            messages.warning(request, "Please draw your signature or upload an image before saving.")

    return render(request, 'edit_profile.html', {
        'profile': profile,
        'next_url': next_url,
        'next_name': next_name,
    })


@login_required
def check_user_signature(request):
    try:
        from django.http import JsonResponse
        profile = getattr(request.user, 'profile', None)
        has_sig = bool(profile and profile.signature)
        return JsonResponse({
            'has_signature': has_sig,
        })
    except Exception as e:
        from django.http import JsonResponse
        return JsonResponse({'has_signature': False, 'error': str(e)})


# 📥 INBOX VIEW
@login_required
def notesheet_inbox(request):
    from django.db.models import Q
    from django.utils import timezone

    # Mark unseen notesheets currently with user as seen upon accessing inbox
    Notesheet.objects.filter(
        current_holder=request.user,
        is_seen=False
    ).update(is_seen=True, seen_at=timezone.now())

    forwarded_ids = NotesheetForward.objects.filter(
        Q(forwarded_by=request.user) | Q(forwarded_to=request.user)
    ).values_list('notesheet_id', flat=True)
    
    returned_ids = NotesheetReturn.objects.filter(
        Q(returned_by=request.user) | Q(returned_to=request.user)
    ).values_list('notesheet_id', flat=True)

    notesheets = Notesheet.objects.filter(
        Q(current_holder=request.user) | 
        Q(id__in=forwarded_ids) | 
        Q(id__in=returned_ids)
    ).distinct().order_by('-updated_at')
    
    return render(request, 'notesheet_inbox.html', {'notesheets': notesheets})


@login_required
def api_unread_counts(request):
    """
    Returns real-time unread count totals for sidebar badges and notification icon.
    """
    from django.http import JsonResponse
    from .models import Notesheet, Letter, Notification, Task, VehicleRequisition, Commitment

    unread_ns_count = Notesheet.objects.filter(
        current_holder=request.user,
        is_seen=False
    ).count()

    unread_letters_count = Letter.objects.filter(
        receiver=request.user,
        is_read=False,
        is_draft=False
    ).count()
    
    unread_tasks_count = Task.objects.filter(
        assigned_to=request.user,
        status='Pending'
    ).count()
    
    unread_requisitions_count = VehicleRequisition.objects.filter(manager_admin=request.user).exclude(status__in=['Completed', 'Rejected']).count()
    unread_commitments_count = Commitment.objects.filter(
        invited_managers=request.user,
        is_sent_to_manager=True,
        status='Pending'
    ).count()

    unread_notifs_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()

    return JsonResponse({
        'status': 'success',
        'unread_notesheets_count': unread_ns_count,
        'unread_letters_count': unread_letters_count,
        'unread_tasks_count': unread_tasks_count,
        'unread_requisitions_count': unread_requisitions_count,
        'unread_commitments_count': unread_commitments_count,
        'unread_notifications_count': unread_notifs_count,
    })



# 📤 OUTBOX VIEW
@login_required
def notesheet_outbox(request):
    notesheets = Notesheet.objects.filter(
        created_by=request.user
    ).exclude(current_holder=request.user).order_by('-updated_at')
    return render(request, 'notesheet_outbox.html', {'notesheets': notesheets})

# =========================================================
# LETTER REPLY VIEWS
# =========================================================
@login_required
def reply_letter(request, letter_id):
    from .models import LetterReplyAttachment
    letter = get_object_or_404(Letter, id=letter_id)
    
    # Only receiver can reply, and only if not already replied
    if request.user != letter.receiver:
        messages.error(request, "You are not authorized to reply to this letter.")
        return redirect('letter_inbox')
        
    if letter.reply_text:
        messages.info(request, "You have already replied to this letter.")
        return redirect('view_letter_reply', letter_id=letter.id)
        
    if request.method == 'POST':
        reply_text = request.POST.get('reply_text')
        reply_files = request.FILES.getlist('reply_attachments')
        
        if reply_text:
            from django.utils import timezone
            letter.reply_text = reply_text
            # Backward compatibility: save first file to old field
            if reply_files:
                letter.reply_attachment = reply_files[0]
            letter.reply_date = timezone.now()
            letter.save()
            
            # Save all files to LetterReplyAttachment
            for f in reply_files:
                LetterReplyAttachment.objects.create(letter=letter, file=f)
            
            messages.success(request, "Reply submitted successfully!")
            return redirect('letter_inbox')
        else:
            messages.error(request, "Reply text cannot be empty.")
            
    return render(request, 'reply_letter.html', {'letter': letter})

@login_required
def view_letter_reply(request, letter_id):
    letter = get_object_or_404(Letter, id=letter_id)
    
    # Only sender and receiver can view the reply
    if request.user != letter.sender and request.user != letter.receiver:
        messages.error(request, "You are not authorized to view this reply.")
        return redirect('letter_inbox')
        
    if not letter.reply_text:
        messages.info(request, "No reply has been sent for this letter yet.")
        return redirect('letter_detail', letter_id=letter.id)
        
    return render(request, 'view_letter_reply.html', {'letter': letter})

@login_required
def mark_notification_as_read(request, notification_id):
    from django.http import JsonResponse
    from .models import Notification
    
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    
    # If the request is AJAX, return JsonResponse with the link
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'link': notification.link})
        
    # Otherwise redirect to the link if it exists
    if notification.link:
        return redirect(notification.link)
    
    return redirect(request.META.get('HTTP_REFERER', '/'))

# =========================================================
# VEHICLE REQUISITION VIEWS
# =========================================================
@login_required
def requisition_list(request):
    from .models import VehicleRequisition
    
    is_manager = False
    if hasattr(request.user, 'profile') and request.user.profile.role:
        if request.user.profile.role.category in ['ZM', 'Manager', 'GM', 'CEO'] or request.user.profile.role.code in ['Manager_Admin', 'Fleet_Manager', 'MngrFleet']:
            is_manager = True
            
    if is_manager:
        from django.db.models import Q
        from .models import VehicleRequisitionForward
        forwarded_ids = VehicleRequisitionForward.objects.filter(
            Q(forwarded_by=request.user) | Q(forwarded_to=request.user)
        ).values_list('requisition_id', flat=True)
        
        requisitions = VehicleRequisition.objects.filter(
            Q(manager_admin=request.user) | Q(id__in=forwarded_ids)
        ).distinct().order_by('-created_at')
    else:
        requisitions = VehicleRequisition.objects.filter(fleet_officer=request.user).order_by('-created_at')
        is_manager = False
    
    return render(request, 'requisition_list.html', {
        'requisitions': requisitions,
        'is_manager': is_manager
    })

@login_required
def create_requisition(request):
    from .models import VehicleRequisition
    from .forms import VehicleRequisitionForm
    from django.contrib.auth.models import User

    from django.db.models import Q
    from .models import UserHierarchy
    
    # --- Always define user_zone for the template ---
    user_zone = request.user.profile.zone if hasattr(request.user, 'profile') else None
    
    hierarchy = UserHierarchy.objects.filter(boss=request.user).first()
    
    if hierarchy and hierarchy.requisition_subs.exists():
        recipient_users = hierarchy.requisition_subs.all()
    else:
        if user_zone:
            recipient_users = User.objects.filter(
                Q(profile__zone=user_zone, profile__role__category__in=['ZM', 'Manager', 'GM', 'CEO']) |
                Q(profile__role__code__in=['MngrFleet', 'Manager_Admin', 'Fleet_Manager'])
            ).distinct()
        else:
            recipient_users = User.objects.filter(
                Q(profile__role__category__in=['ZM', 'Manager', 'GM', 'CEO']) |
                Q(profile__role__code__in=['MngrFleet', 'Manager_Admin', 'Fleet_Manager'])
            ).distinct()

    recipient_list = []
    for u in recipient_users:
        if hasattr(u, 'profile') and u.profile.role:
            role_code = u.profile.role.code or u.profile.role.name
            u.display_label = role_code
        else:
            u.display_label = u.get_full_name() or u.username
        recipient_list.append(u)

    if request.method == "POST":
        # Combine the 4 separate issue fields into one issue_description
        post_data = request.POST.copy()
        issues = []
        for i in range(1, 5):
            val = post_data.get(f'issue_{i}', '').strip()
            if val:
                issues.append(f'({i}) {val}')
        if issues:
            post_data['issue_description'] = '\n'.join(issues)

        form = VehicleRequisitionForm(post_data, request.FILES)
        if form.is_valid():
            req = form.save(commit=False)
            req.fleet_officer = request.user

            # Fetch the selected recipient from the dropdown
            recipient_id = request.POST.get('send_to_manager')
            try:
                recipient = User.objects.get(id=recipient_id)
                req.manager_admin = recipient
            except (User.DoesNotExist, TypeError, ValueError):
                messages.error(request, "Please select a valid recipient.")
                from .models import Zone
                from logbook.models import Vehicle
                import json
                _zones = Zone.objects.all().order_by('name')
                _vbz = {}
                for _v in Vehicle.objects.select_related('zone','driver').filter(status='Active'):
                    _zid = str(_v.zone_id) if _v.zone_id else '0'
                    _vbz.setdefault(_zid, []).append({'id':_v.id,'vehicle_name':_v.vehicle_name,'vehicle_id_number':_v.vehicle_id_number or '','driver_name':_v.driver.name if _v.driver else '','driver_mobile':_v.driver.mobile if _v.driver else '','driver_cnic':_v.driver.cnic if _v.driver else ''})
                return render(request, 'create_requisition.html', {
                    'form': form,
                    'recipient_list': recipient_list,
                    'zones': _zones,
                    'vehicles_by_zone_json': json.dumps(_vbz),
                })

            # Handle Signatures
            import base64
            from django.core.files.base import ContentFile
            import uuid

            driver_sig_data = request.POST.get('driver_signature_data')
            if driver_sig_data:
                fmt, imgstr = driver_sig_data.split(';base64,')
                ext = fmt.split('/')[-1]
                req.driver_signature = ContentFile(base64.b64decode(imgstr), name=f'driver_sig_{uuid.uuid4()}.{ext}')

            fleet_sig_data = request.POST.get('fleet_officer_signature_data')
            if fleet_sig_data:
                fmt, imgstr = fleet_sig_data.split(';base64,')
                ext = fmt.split('/')[-1]
                req.fleet_officer_signature = ContentFile(base64.b64decode(imgstr), name=f'fleet_sig_{uuid.uuid4()}.{ext}')
            elif hasattr(request.user, 'profile') and request.user.profile.signature:
                req.fleet_officer_signature = request.user.profile.signature

            req.save()

            # Handle multiple file attachments
            from .models import VehicleRequisitionAttachment
            attachment_files = request.FILES.getlist('requisition_attachments')
            for attachment_file in attachment_files:
                VehicleRequisitionAttachment.objects.create(
                    requisition=req,
                    file=attachment_file,
                    original_name=attachment_file.name
                )

            # Send Notification to selected recipient
            create_notification(
                recipient=recipient,
                sender=request.user,
                title="New Vehicle Requisition",
                message=f"{request.user.get_full_name() or request.user.username} submitted a requisition for vehicle {req.vehicle_number}.",
                link=f"/requisitions/",
                notification_type='notesheet'
            )

            messages.success(request, "Requisition form submitted successfully.")
            return redirect('requisition_list')
    else:
        form = VehicleRequisitionForm()

    from .models import Zone
    from logbook.models import Vehicle
    zones = Zone.objects.all().order_by('name')
    # Pre-build vehicles grouped by zone as JSON for JS
    import json
    vehicles_by_zone = {}
    for v in Vehicle.objects.prefetch_related('drivers').select_related('zone', 'driver').filter(status='Active'):
        zid = str(v.zone_id) if v.zone_id else '0'
        if zid not in vehicles_by_zone:
            vehicles_by_zone[zid] = []
        actual_driver = v.driver or v.drivers.filter(is_active=True).first()
        vehicles_by_zone[zid].append({
            'id': v.id,
            'vehicle_name': v.vehicle_name,
            'vehicle_id_number': v.vehicle_id_number or '',
            'driver_name': actual_driver.name if actual_driver else '',
            'driver_mobile': actual_driver.mobile if actual_driver else '',
            'driver_cnic': actual_driver.cnic if actual_driver else '',
        })
    return render(request, 'create_requisition.html', {
        'form': form,
        'recipient_list': recipient_list,
        'zones': zones,
        'vehicles_by_zone_json': json.dumps(vehicles_by_zone),
        'user_zone_id': user_zone.id if user_zone else None,
    })

@login_required
def update_requisition_status(request, pk):
    from .models import VehicleRequisition
    is_manager = False
    if hasattr(request.user, 'profile') and request.user.profile.role:
        if request.user.profile.role.category in ['ZM', 'Manager', 'GM', 'CEO'] or request.user.profile.role.code in ['Manager_Admin', 'Fleet_Manager', 'MngrFleet']:
            is_manager = True
            
    if request.method == "POST" and is_manager:
        req = get_object_or_404(VehicleRequisition, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(VehicleRequisition.STATUS_CHOICES):
            req.status = new_status
            req.save()
            
            # Notify the Fleet Officer
            create_notification(
                recipient=req.fleet_officer,
                sender=request.user,
                title="Requisition Status Updated",
                message=f"Your requisition for {req.vehicle_number} is now {new_status}.",
                link=f"/requisitions/",
                notification_type='notesheet'
            )
            messages.success(request, f"Requisition status updated to {new_status}.")
            
    return redirect('requisition_list')

@login_required
def view_requisition(request, pk):
    from .models import VehicleRequisition, VehicleRequisitionAttachment
    req = get_object_or_404(VehicleRequisition, pk=pk)
    
    # Only allow the fleet officer who created it, or managers to view it
    is_manager = False
    if hasattr(request.user, 'profile') and request.user.profile.role:
        if request.user.profile.role.category in ['ZM', 'Manager', 'GM', 'CEO'] or request.user.profile.role.code in ['Manager_Admin', 'Fleet_Manager', 'MngrFleet']:
            is_manager = True
            
    if req.fleet_officer != request.user and not is_manager:
        messages.error(request, "You are not authorized to view this requisition.")
        return redirect('requisition_list')
        
    try:
        attachments = VehicleRequisitionAttachment.objects.filter(requisition=req)
    except Exception:
        attachments = getattr(req, 'attachments', [])
        
    forwards = req.forwards.all().order_by('forwarded_at')
        
    # Build recipient list for ANYONE who is the current holder (manager_admin)
    from django.contrib.auth.models import User
    from django.db.models import Q
    recipient_list = []
    
    # The current "holder" is whoever is req.manager_admin
    is_current_holder = (req.manager_admin == request.user)
    
    if is_current_holder:
        from .models import UserHierarchy
        hierarchy = UserHierarchy.objects.filter(boss=request.user).first()
        
        if hierarchy and hierarchy.requisition_subs.exists():
            recipient_users = hierarchy.requisition_subs.all()
        else:
            user_zone = request.user.profile.zone if hasattr(request.user, 'profile') else None
            if user_zone:
                recipient_users = User.objects.filter(
                    Q(profile__zone=user_zone, profile__role__category__in=['ZM', 'Manager', 'GM', 'CEO']) |
                    Q(profile__role__code__in=['MngrFleet', 'Manager_Admin', 'Fleet_Manager'])
                ).distinct()
            else:
                recipient_users = User.objects.filter(
                    Q(profile__role__category__in=['ZM', 'Manager', 'GM', 'CEO']) |
                    Q(profile__role__code__in=['MngrFleet', 'Manager_Admin', 'Fleet_Manager'])
                ).distinct()
        
        for u in recipient_users:
            if u == request.user:
                continue
            if hasattr(u, 'profile') and u.profile.role:
                role_code = u.profile.role.code or u.profile.role.name
                u.display_label = role_code
            else:
                u.display_label = u.get_full_name() or u.username
            recipient_list.append(u)

    # Check if user is a fleet officer (fzone user)
    is_fleet_officer = 'fozone' in request.user.username.lower() or 'fleet_officer' in request.user.username.lower()

    return render(request, 'view_requisition.html', {
        'req': req,
        'is_manager': is_manager,
        'is_current_holder': is_current_holder,
        'attachments': attachments,
        'recipient_list': recipient_list,
        'forwards': forwards,
        'is_fleet_officer': is_fleet_officer,
    })

@login_required
def forward_requisition(request, pk):
    from .models import VehicleRequisition, Notification
    from django.contrib.auth.models import User
    
    if request.method == "POST":
        req = get_object_or_404(VehicleRequisition, pk=pk)
        
        if req.manager_admin != request.user:
            messages.error(request, "You are not the current holder of this requisition.")
            return redirect('requisition_list')
            
        forward_to_id = request.POST.get('forward_to')
        remark = request.POST.get('remark', '').strip()
        new_status = request.POST.get('status')

        if new_status and new_status in dict(VehicleRequisition.STATUS_CHOICES):
            req.status = new_status
            req.save()
        if forward_to_id:
            try:
                new_admin = User.objects.get(id=forward_to_id)
                req.manager_admin = new_admin
                req.save()
                
                from .models import VehicleRequisitionForward
                fw = VehicleRequisitionForward(
                    requisition=req,
                    forwarded_by=request.user,
                    forwarded_to=new_admin,
                    remark=remark,
                    status_at_forward=req.status
                )
                
                # Check if forwarded_by is a fleet officer and handle attachments
                is_fleet_officer = 'fozone' in request.user.username.lower() or 'fleet_officer' in request.user.username.lower()
                if is_fleet_officer:
                    fw.is_fleet_officer_remark = True
                    attachment_files = request.FILES.getlist('remark_attachments')
                    att_fields = ['attachment_1', 'attachment_2', 'attachment_3', 'attachment_4', 'attachment_5']
                    for i, att_file in enumerate(attachment_files[:5]):
                        setattr(fw, att_fields[i], att_file)
                
                fw.save()
                
                # Notify the new manager
                from .models import Notification
                Notification.objects.create(
                    recipient=new_admin,
                    sender=request.user,
                    title="Requisition Forwarded",
                    message=f"Requisition for {req.vehicle_number} has been forwarded to you by {request.user.get_full_name() or request.user.username}.",
                    link=f"/requisitions/view/{req.id}/",
                    notification_type='notesheet'
                )
                
                messages.success(request, f"Requisition forwarded to {new_admin.get_full_name() or new_admin.username} successfully.")
            except User.DoesNotExist:
                messages.error(request, "Selected user does not exist.")
        else:
            messages.error(request, "Please select a user to forward to.")
            
    return redirect('requisition_list')


@login_required
def edit_requisition(request, pk):
    from .models import VehicleRequisition, VehicleRequisitionAttachment
    from .forms import VehicleRequisitionForm
    from django.contrib.auth.models import User
    from django.db.models import Q

    req = get_object_or_404(VehicleRequisition, pk=pk)
    
    # 1. Sirf wahi Fleet Officer edit kar sakta hai jisne requisition create ki ho
    if req.fleet_officer != request.user:
        messages.error(request, "You are not authorized to edit this requisition.")
        return redirect('requisition_list')
        
    # 2. Strict Check: Agar status 'Pending' NAHI hai, to edit blocked hoga
    if req.status != 'Pending':
        messages.error(request, f"Cannot edit this requisition. It is already '{req.status}'.")
        return redirect('requisition_list')

    # Build recipient list for manager selection (Same as create_requisition)
    user_zone = request.user.profile.zone if hasattr(request.user, 'profile') else None
    if user_zone:
        recipient_users = User.objects.filter(
            Q(profile__zone=user_zone, profile__role__category__in=['ZM', 'Manager', 'GM', 'CEO']) |
            Q(profile__role__code__in=['MngrFleet', 'Manager_Admin', 'Fleet_Manager'])
        ).distinct()
    else:
        recipient_users = User.objects.filter(
            Q(profile__role__category__in=['ZM', 'Manager', 'GM', 'CEO']) |
            Q(profile__role__code__in=['MngrFleet', 'Manager_Admin', 'Fleet_Manager'])
        ).distinct()

    recipient_list = []
    for u in recipient_users:
        if hasattr(u, 'profile') and u.profile.role:
            role_name = u.profile.role.name
            zone_name = f" — {u.profile.zone.name}" if u.profile.zone else ""
            u.display_label = f"{role_name}{zone_name}"
        else:
            u.display_label = u.get_full_name() or u.username
        recipient_list.append(u)

    if request.method == "POST":
        post_data = request.POST.copy()
        
        # Combine issues 1 to 4
        issues = []
        for i in range(1, 5):
            val = post_data.get(f'issue_{i}', '').strip()
            if val:
                issues.append(f'({i}) {val}')
        if issues:
            post_data['issue_description'] = '\n'.join(issues)

        form = VehicleRequisitionForm(post_data, request.FILES, instance=req)
        if form.is_valid():
            updated_req = form.save(commit=False)

            # Update Recipient Manager if changed
            recipient_id = request.POST.get('send_to_manager')
            if recipient_id:
                try:
                    updated_req.manager_admin = User.objects.get(id=recipient_id)
                except User.DoesNotExist:
                    pass

            # Handle Signatures Update
            import base64
            from django.core.files.base import ContentFile
            import uuid

            driver_sig_data = request.POST.get('driver_signature_data')
            if driver_sig_data:
                fmt, imgstr = driver_sig_data.split(';base64,')
                ext = fmt.split('/')[-1]
                updated_req.driver_signature = ContentFile(base64.b64decode(imgstr), name=f'driver_sig_{uuid.uuid4()}.{ext}')

            fleet_sig_data = request.POST.get('fleet_officer_signature_data')
            if fleet_sig_data:
                fmt, imgstr = fleet_sig_data.split(';base64,')
                ext = fmt.split('/')[-1]
                updated_req.fleet_officer_signature = ContentFile(base64.b64decode(imgstr), name=f'fleet_sig_{uuid.uuid4()}.{ext}')

            updated_req.save()

            # Handle New File Attachments
            attachment_files = request.FILES.getlist('requisition_attachments')
            for attachment_file in attachment_files:
                VehicleRequisitionAttachment.objects.create(
                    requisition=updated_req,
                    file=attachment_file,
                    original_name=attachment_file.name
                )

            messages.success(request, "Requisition updated successfully.")
            return redirect('requisition_list')
    else:
        form = VehicleRequisitionForm(instance=req)

    from .models import Zone
    from logbook.models import Vehicle
    zones = Zone.objects.all().order_by('name')
    import json
    vehicles_by_zone = {}
    for v in Vehicle.objects.prefetch_related('drivers').select_related('zone', 'driver').filter(status='Active'):
        zid = str(v.zone_id) if v.zone_id else '0'
        if zid not in vehicles_by_zone:
            vehicles_by_zone[zid] = []
        actual_driver = v.driver or v.drivers.filter(is_active=True).first()
        vehicles_by_zone[zid].append({
            'id': v.id,
            'vehicle_name': v.vehicle_name,
            'vehicle_id_number': v.vehicle_id_number or '',
            'driver_name': actual_driver.name if actual_driver else '',
            'driver_mobile': actual_driver.mobile if actual_driver else '',
            'driver_cnic': actual_driver.cnic if actual_driver else '',
        })
    # For edit, use the requisition's zone id to pre-select
    edit_zone_id = req.zone if req.zone else None
    # Try to parse it as int (zone name stored as string in old records)
    try:
        from .models import Zone as ZoneModel
        zone_obj = ZoneModel.objects.filter(name=edit_zone_id).first() or ZoneModel.objects.filter(id=edit_zone_id).first()
        pre_zone_id = zone_obj.id if zone_obj else (user_zone.id if user_zone else None)
    except Exception:
        pre_zone_id = user_zone.id if user_zone else None
    return render(request, 'create_requisition.html', {
        'form': form,
        'req': req,
        'recipient_list': recipient_list,
        'is_edit': True,
        'zones': zones,
        'vehicles_by_zone_json': json.dumps(vehicles_by_zone),
        'user_zone_id': pre_zone_id,
    })

# =========================================================
# LOG BOOK HISTORY ATTACHMENT APIs
# =========================================================
import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

@login_required
def api_get_logbook_history(request):
    """
    Returns page-based digital logbook data for the selected vehicle.
    """
    from logbook.models import Vehicle, LogBook, LogBookPage
    from logbook.views import is_admin_or_ceo, get_user_zone

    if is_admin_or_ceo(request.user):
        vehicles_qs = Vehicle.objects.all().order_by('vehicle_id_number')
    else:
        user_zone = get_user_zone(request.user)
        if user_zone:
            vehicles_qs = Vehicle.objects.filter(zone=user_zone).order_by('vehicle_id_number')
        else:
            vehicles_qs = Vehicle.objects.none()

    vehicles_data = [
        {
            'id': v.id,
            'vehicle_number': v.vehicle_id_number,
            'registration_number': getattr(v, 'vehicle_name', ''),
            'type': getattr(v, 'vehicle_type', ''),
            'zone': v.zone.title if v.zone else '',
            'current_meter': getattr(v, 'current_meter_reading', 0),
        }
        for v in vehicles_qs
    ]

    vehicle_id = request.GET.get('vehicle_id')
    if not vehicle_id:
        return JsonResponse({'vehicles': vehicles_data, 'pages': [], 'total_pages': 0, 'total_entries': 0})

    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    logbook, _ = LogBook.objects.get_or_create(
        vehicle=vehicle,
        defaults={
            'vehicle_name': vehicle.vehicle_id_number,
            'opening_meter_reading': getattr(vehicle, 'current_meter_reading', 0)
        }
    )

    if logbook.pages.count() == 0:
        initial_pages = [
            LogBookPage(logbook=logbook, page_number=i)
            for i in range(1, 3)
        ]
        LogBookPage.objects.bulk_create(initial_pages)

    # Attach any unassigned entries to Page 1 for backward compatibility
    first_page = logbook.pages.filter(page_number=1).first()
    if first_page:
        logbook.entries.filter(page__isnull=True).update(page=first_page)

    pages_qs = logbook.pages.all().prefetch_related('entries').order_by('page_number')
    total_pages = pages_qs.count()
    total_entries = 0

    pages_list = []
    for p in pages_qs:
        entries_qs = p.entries.all().order_by('date', 'time_from')
        total_entries += entries_qs.count()

        p_entries = [
            {
                'id': e.id,
                'date': e.date.strftime('%Y-%m-%d'),
                'formatted_date': e.date.strftime('%d-%m-%Y'),
                'time_from': e.time_from.strftime('%I:%M %p') if e.time_from else '',
                'time_to': e.time_to.strftime('%I:%M %p') if e.time_to else '',
                'officer_name': e.officer_name or '-',
                'driver_name': e.driver_name or '-',
                'meter_from': e.meter_reading_from,
                'meter_to': e.meter_reading_to,
                'km_covered': e.km_covered,
                'pol_drawn': str(e.pol_drawn),
                'purpose': e.purpose_of_journey or '-',
                'details': e.details_of_journey or '-',
                'remarks': e.remarks or '-',
                'file_url': (
                    f"{e.signed_requisition.url}?v={int(os.path.getmtime(e.signed_requisition.path))}"
                    if e.signed_requisition and os.path.exists(e.signed_requisition.path)
                    else (e.signed_requisition.url if e.signed_requisition else '')
                ),
            }
            for e in entries_qs
        ]

        pages_list.append({
            'id': p.id,
            'page_number': p.page_number,
            'entries_count': len(p_entries),
            'entries': p_entries,
        })

    return JsonResponse({
        'vehicles': vehicles_data,
        'vehicle': {
            'id': vehicle.id,
            'vehicle_number': vehicle.vehicle_id_number,
            'registration_number': getattr(vehicle, 'vehicle_name', '-') or '-',
            'zone': vehicle.zone.title if getattr(vehicle, 'zone', None) else '-',
            'vehicle_type': getattr(vehicle, 'vehicle_type', '-') or '-',
            'current_meter': getattr(vehicle, 'current_meter_reading', 0),
            'logbook_serial': getattr(logbook, 'serial_number', '-'),
            'average_to_litre': str(getattr(logbook, 'average_to_litre', '-')) if getattr(logbook, 'average_to_litre', None) else '-',
        },
        'total_pages': total_pages,
        'total_entries': total_entries,
        'pages': pages_list,
    })


def generate_logbook_history_pdf(vehicle, logbook, pages_qs, officer_name="Fleet Officer"):
    """
    Generates a PDF document for Digital Vehicle Log Book History using ReportLab.
    Always orders pages by page_number ASC.
    """
    import os
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        alignment=1,
        textColor=colors.HexColor('#0d2b1e')
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        alignment=1,
        textColor=colors.HexColor('#059669')
    )

    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1f2937')
    )

    bold_style = ParagraphStyle(
        'BoldText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#111827')
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#111827')
    )

    banner_label_style = ParagraphStyle(
        'BannerLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#64748b')
    )

    banner_val_style = ParagraphStyle(
        'BannerVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#0d2b1e')
    )

    banner_meter_style = ParagraphStyle(
        'BannerMeterVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#059669')
    )

    elements = []

    def fmt_num(val):
        if val is None:
            return '-'
        try:
            return f"{int(val):,}"
        except (ValueError, TypeError):
            return str(val)

    # Modern 4-Column Header Banner (matching Screenshot 3)
    reg_num = getattr(vehicle, 'vehicle_name', None) or getattr(vehicle, 'vehicle_id_number', '-')
    type_zone = f"{getattr(vehicle, 'vehicle_type', '-')} ({getattr(vehicle, 'zone', '-')})"
    meter_reading = f"{fmt_num(getattr(vehicle, 'current_meter_reading', 0))} KM"

    meta_data = [
        [
            Paragraph("VEHICLE", banner_label_style),
            Paragraph("REGISTRATION", banner_label_style),
            Paragraph("TYPE / ZONE", banner_label_style),
            Paragraph("CURRENT METER", banner_label_style),
        ],
        [
            Paragraph(getattr(vehicle, 'vehicle_id_number', getattr(vehicle, 'vehicle_name', '-')), banner_val_style),
            Paragraph(reg_num, banner_val_style),
            Paragraph(type_zone, banner_val_style),
            Paragraph(meter_reading, banner_meter_style),
        ]
    ]

    meta_table = Table(meta_data, colWidths=[130, 130, 130, 130])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0fdf4')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#bbf7d0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('BOTTOMPADDING', (0,0), (-1,0), 1),
        ('TOPPADDING', (0,1), (-1,1), 1),
        ('BOTTOMPADDING', (0,1), (-1,1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # Total Pages & Total Entries summary
    total_pages_cnt = pages_qs.count()
    total_entries_cnt = sum(p.entries.count() for p in pages_qs)

    elements.append(Paragraph(f"<b>DIGITAL LOG BOOK PAGES ({total_pages_cnt} Pages, {total_entries_cnt} Total Entries)</b>", bold_style))
    elements.append(Spacer(1, 8))

    # Render Each Page Section
    for page in pages_qs:
        page_entries = list(page.entries.all().order_by('date', 'time_from'))
        elements.append(Paragraph(f"<b>PAGE NO. {page.page_number}</b> &nbsp;&nbsp;<font color='#64748b'>({len(page_entries)} Entries)</font>", bold_style))
        elements.append(Spacer(1, 4))

        if page_entries:
            history_headers = ["#", "Date", "Officer/Driver", "Details of Journey", "Purpose", "Meter From-To", "KM"]
            table_data = [[Paragraph(h, table_header_style) for h in history_headers]]

            for idx, e in enumerate(page_entries, 1):
                table_data.append([
                    Paragraph(str(idx), table_cell_style),
                    Paragraph(e.date.strftime('%d-%m-%Y') if e.date else '-', table_cell_style),
                    Paragraph(e.officer_name or e.driver_name or '-', table_cell_style),
                    Paragraph(e.details_of_journey or '-', table_cell_style),
                    Paragraph(e.purpose_of_journey or '-', table_cell_style),
                    Paragraph(f"{fmt_num(e.meter_reading_from)} &rarr; {fmt_num(e.meter_reading_to)}", table_cell_style),
                    Paragraph(f"{fmt_num(e.km_covered)} km", table_cell_style),
                ])

            history_table = Table(table_data, colWidths=[20, 65, 95, 150, 90, 70, 30])
            history_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0d2b1e')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
                ('PADDING', (0,0), (-1,-1), 4),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')])
            ]))
            elements.append(history_table)
        else:
            empty_table = Table([[Paragraph(f"<i>Log Book Not Attached Yet (Page {page.page_number})</i>", normal_style)]], colWidths=[520])
            empty_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            elements.append(empty_table)

        elements.append(Spacer(1, 10))

    doc.build(elements)
    buffer.seek(0)
    summary_pdf_bytes = buffer.getvalue()

    # Find attached scanned PDF documents to append
    attached_pdf_paths = []
    for page in pages_qs:
        for entry in page.entries.all():
            if entry.signed_requisition and hasattr(entry.signed_requisition, 'path') and os.path.exists(entry.signed_requisition.path):
                fpath = entry.signed_requisition.path
                if fpath.lower().endswith('.pdf') and fpath not in attached_pdf_paths:
                    attached_pdf_paths.append(fpath)

    # Return attached scanned PDF files directly without summary table cover page
    if attached_pdf_paths:
        try:
            import pypdf
            writer = pypdf.PdfWriter()
            for pdf_p in attached_pdf_paths:
                try:
                    reader_attached = pypdf.PdfReader(pdf_p)
                    for p in reader_attached.pages:
                        writer.add_page(p)
                except Exception:
                    pass

            if len(writer.pages) > 0:
                merged_buffer = BytesIO()
                writer.write(merged_buffer)
                merged_buffer.seek(0)
                return merged_buffer.getvalue()
        except Exception:
            pass

    return summary_pdf_bytes


@login_required
def api_attach_logbook_history(request):
    """
    Generates Digital Log Book history PDF report and attaches it as a NotesheetAttachment.
    """
    if request.method != "POST":
        return JsonResponse({'error': 'POST required'}, status=405)

    vehicle_id = request.POST.get('vehicle_id')
    notesheet_id = request.POST.get('notesheet_id')

    if not vehicle_id:
        return JsonResponse({'error': 'Vehicle ID is required.'}, status=400)

    from logbook.models import Vehicle, LogBook, LogBookPage
    from .models import Notesheet, NotesheetAttachment

    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    logbook, _ = LogBook.objects.get_or_create(
        vehicle=vehicle,
        defaults={
            'vehicle_name': getattr(vehicle, 'vehicle_id_number', ''),
            'opening_meter_reading': getattr(vehicle, 'current_meter_reading', 0)
        }
    )

    if logbook.pages.count() == 0:
        initial_pages = [
            LogBookPage(logbook=logbook, page_number=i)
            for i in range(1, 3)
        ]
        LogBookPage.objects.bulk_create(initial_pages)

    pages_qs = logbook.pages.all().prefetch_related('entries').order_by('page_number')

    officer_name = request.user.get_full_name() or request.user.username
    pdf_bytes = generate_logbook_history_pdf(
        vehicle=vehicle,
        logbook=logbook,
        pages_qs=pages_qs,
        officer_name=officer_name
    )

    filename = f"Vehicle {getattr(vehicle, 'vehicle_id_number', getattr(vehicle, 'vehicle_name', 'Unknown'))} - Digital Log Book History.pdf"

    if notesheet_id:
        notesheet = get_object_or_404(Notesheet, id=notesheet_id)
        attachment = NotesheetAttachment.objects.create(
            notesheet=notesheet,
            file=ContentFile(pdf_bytes, name=filename),
            flag_name='LogBook'
        )
        return JsonResponse({
            'success': True,
            'attachment_id': attachment.id,
            'filename': filename,
            'url': attachment.file.url,
            'flag_name': 'LogBook',
            'notesheet_id': notesheet.id
        })
    else:
        from django.core.files.storage import default_storage
        file_path = default_storage.save(f"notesheet_attachments/{filename}", ContentFile(pdf_bytes, name=filename))
        file_url = default_storage.url(file_path)

        return JsonResponse({
            'success': True,
            'filename': filename,
            'file_path': file_path,
            'url': file_url,
            'flag_name': 'LogBook'
        })


from django.views.decorators.clickjacking import xframe_options_exempt

@login_required
@xframe_options_exempt
def view_document_inline(request):
    """
    Serves files inline (Content-Disposition: inline) so PDF files open directly in browser.
    """
    import os
    import mimetypes
    from urllib.parse import unquote
    from django.conf import settings
    from django.http import HttpResponseNotFound, HttpResponse

    raw_url = request.GET.get('url', '')
    raw_path = request.GET.get('path', '')

    url = unquote(raw_url)
    file_path = unquote(raw_path)

    if url:
        if '/media/' in url:
            file_path = url.split('/media/')[-1]
        else:
            file_path = url

    if not file_path:
        return HttpResponseNotFound("No file path specified.")

    file_path = unquote(file_path).replace('..', '').lstrip('/')
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        # Fallback: search in MEDIA_ROOT / notesheet_attachments / basename
        base_name = os.path.basename(file_path)
        alt_path = os.path.join(settings.MEDIA_ROOT, 'notesheet_attachments', base_name)
        if os.path.exists(alt_path) and os.path.isfile(alt_path):
            full_path = alt_path

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return HttpResponseNotFound(f"File not found on server: {os.path.basename(file_path)}")

    content_type, _ = mimetypes.guess_type(full_path)
    if not content_type:
        content_type = 'application/pdf' if full_path.lower().endswith('.pdf') else 'application/octet-stream'

    with open(full_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(full_path)}"'
        response['X-Frame-Options'] = 'ALLOWALL'
        return response



@login_required
def get_vehicles_by_zone(request):
    """Returns active vehicles for a given zone as JSON for the requisition form dropdown."""
    from logbook.models import Vehicle
    zone_id = request.GET.get('zone_id')
    if not zone_id:
        return JsonResponse({'vehicles': []})
    vehicles = Vehicle.objects.filter(
        zone_id=zone_id, status='Active'
    ).select_related('driver').order_by('vehicle_name')
    data = []
    for v in vehicles:
        data.append({
            'id': v.id,
            'vehicle_name': v.vehicle_name,
            'vehicle_id_number': v.vehicle_id_number or '',
            'driver_name': v.driver.name if v.driver else '',
            'driver_mobile': v.driver.mobile if v.driver else '',
            'driver_cnic': v.driver.cnic if v.driver else '',
        })
    return JsonResponse({'vehicles': data})


@login_required
def get_vehicle_logbook(request):
    """Returns logbook info for a given vehicle."""
    from logbook.models import Vehicle, LogBook
    vehicle_id = request.GET.get('vehicle_id')
    try:
        vehicle = Vehicle.objects.get(pk=vehicle_id)
        logbook = vehicle.logbook  # OneToOne relation
        data = {
            'has_logbook': True,
            'logbook_id': logbook.id,
            'title': str(logbook),
        }
    except (Vehicle.DoesNotExist, LogBook.DoesNotExist, Exception):
        data = {'has_logbook': False}
    return JsonResponse(data)