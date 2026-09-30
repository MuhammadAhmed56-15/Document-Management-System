from .models import Notesheet, Notification, Letter, Task, VehicleRequisition, Commitment

def unread_notesheets(request):
    if request.user.is_authenticated:
        notesheets_count = Notesheet.objects.filter(
            current_holder=request.user,
            is_seen=False
        ).count()
        
        letters_count = Letter.objects.filter(
            receiver=request.user,
            is_read=False,
            is_draft=False
        ).count()
        
        tasks_count = Task.objects.filter(
            assigned_to=request.user,
            status='Pending'
        ).count()
        
        is_manager = False
        if hasattr(request.user, 'profile') and request.user.profile.role:
            if request.user.profile.role.category in ['ZM', 'Manager', 'GM', 'CEO'] or request.user.profile.role.code in ['Manager_Admin', 'Fleet_Manager', 'MngrFleet']:
                is_manager = True
                
        requisitions_count = VehicleRequisition.objects.filter(manager_admin=request.user).exclude(status__in=['Completed', 'Rejected']).count()
            
        commitments_count = Commitment.objects.filter(
            invited_managers=request.user,
            is_sent_to_manager=True,
            status='Pending'
        ).count()
        
        return {
            'unread_notesheets_count': notesheets_count,
            'unread_letters_count': letters_count,
            'unread_tasks_count': tasks_count,
            'unread_requisitions_count': requisitions_count,
            'unread_commitments_count': commitments_count,
        }
    return {
        'unread_notesheets_count': 0,
        'unread_letters_count': 0,
        'unread_tasks_count': 0,
        'unread_requisitions_count': 0,
        'unread_commitments_count': 0,
    }

def notifications_processor(request):
    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False)[:5]
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {
            'unread_notifications': unread_notifications,
            'unread_notifications_count': unread_count
        }
    return {}
