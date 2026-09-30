from django.urls import path, include
from . import views
from .views import approve_commitment, reject_commitment

urlpatterns = [
    # Authentication
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboards
    path('ps/', views.ps_dashboard, name='ps_dashboard'),
    path('ceo/', views.ceo_dashboard, name='ceo_dashboard'),
    path('manager/', views.manager_dashboard, name='manager_dashboard'),
    path('gm/', views.gm_dashboard, name='gm_dashboard'),

    # Chart Data API Endpoints
    path('api/chart-data/', views.get_chart_data, name='get_chart_data'),
    path('api/ps-chart-data/', views.get_ps_chart_data, name='get_ps_chart_data'),
    path('gm-chart-data/', views.gm_chart_data, name='gm_chart_data'),
    
    # Commitments
    path('commitment/add/', views.add_commitment, name='add_commitment'),
    path('commitment/edit/<int:pk>/', views.edit_commitment, name='edit_commitment'),
    path('commitment/delete/<int:pk>/', views.delete_commitment, name='delete_commitment'),
    path('commitment/list/', views.commitment_list, name='commitment_list'),
    path('commitment/report/', views.commitment_report, name='commitment_report'),
    
    # Status Updates
    path('update-status/<int:pk>/<str:status>/', views.update_status, name='update_status'),
    path('approve/<int:id>/', approve_commitment, name='approve_commitment'),
    path('reject/<int:id>/', reject_commitment, name='reject_commitment'),
    
    # Manager Tasks
    path('manager/tasks/', views.manager_task_view, name='manager_tasks'),
    path('manager/add-remark/', views.add_remark_view, name='add_remark'),
    path('task/feedbacks/<int:task_id>/', views.task_feedback_detail_view, name='task_feedback_detail'),
    
    # Task Assignment
    path('assign-task/', views.assign_task_view, name='ceo_assign_task'),
    path('all-tasks/', views.all_tasks_view, name='all_tasks'),
    
    # Feedbacks
    path('ceo/view-feedbacks/', views.view_feedbacks, name='ceo_view_feedbacks'),
    path('view-feedbacks/', views.view_feedbacks, name='view_feedbacks'),

    # =========================================================
    # FILE SYSTEM URLs
    # =========================================================
    path('notesheet-files/', views.notesheet_files, name='notesheet_files'),
    path('create-file/', views.create_file, name='create_file'),
    path('file/<int:file_id>/', views.file_detail, name='file_detail'),

    # =========================================================
    # NOTESHEET SYSTEM URLs
    # =========================================================
    path('notesheet/initiate/', views.initiate_notesheet, name='initiate_notesheet'),
    path('notesheet/inbox/', views.notesheet_inbox, name='notesheet_inbox'),
    path('notesheet/outbox/', views.notesheet_outbox, name='notesheet_outbox'),
    path('notesheet/view/<int:task_id>/', views.view_notesheet, name='view_notesheet'),
    path('notesheet-detail/<int:task_id>/', views.notesheet_detail, name='view_notesheet_detail'), 
    
    # LogBook History Attachment APIs & Inline Document Viewer
    path('api/unread-counts/', views.api_unread_counts, name='api_unread_counts'),
    path('api/logbook-history/', views.api_get_logbook_history, name='api_get_logbook_history'),
    path('api/attach-logbook-history/', views.api_attach_logbook_history, name='api_attach_logbook_history'),
    path('view-document/', views.view_document_inline, name='view_document_inline'),

    # Forward and Return Workflow
    path('notesheet/forward/<int:pk>/', views.forward_notesheet, name='forward_notesheet'),
    path('notesheet/return/<int:pk>/', views.return_notesheet, name='return_notesheet'),

    # =========================================================
    # LETTER SYSTEM URLs
    # =========================================================
    path('letters/files/', views.letter_files_list, name='letter_files_list'),
    path('letters/files/create/', views.create_letter_file, name='create_letter_file'),
    path('letters/new/', views.create_letter, name='create_letter'),
    path('letters/inbox/', views.letter_inbox, name='letter_inbox'),
    path('letters/outbox/', views.letter_outbox, name='letter_outbox'),
    path('letters/drafts/', views.letter_drafts, name='letter_drafts'),
    path('letters/send-draft/<int:letter_id>/', views.send_draft_letter, name='send_draft_letter'),
    path('letters/detail/<int:letter_id>/', views.letter_detail, name='letter_detail'),
    path('letters/reply/<int:letter_id>/', views.reply_letter, name='reply_letter'),
    path('letters/view-reply/<int:letter_id>/', views.view_letter_reply, name='view_letter_reply'),
    path('profile/signature/', views.edit_profile_signature, name='edit_profile_signature'),
    path('profile/signature/check/', views.check_user_signature, name='check_user_signature'),

    # =========================================================
    # NOTIFICATIONS URL
    # =========================================================
    path('notifications/read/<int:notification_id>/', views.mark_notification_as_read, name='mark_notification_as_read'),

    # =========================================================
    # VEHICLE REQUISITION URLs
    # =========================================================
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/new/', views.create_requisition, name='create_requisition'),
    path('requisitions/view/<int:pk>/', views.view_requisition, name='view_requisition'),
   
    path('requisitions/update/<int:pk>/', views.update_requisition_status, name='update_requisition_status'),
    path('requisitions/<int:pk>/edit/', views.edit_requisition, name='edit_requisition'),
    path('requisitions/forward/<int:pk>/', views.forward_requisition, name='forward_requisition'),
    path('api/get-vehicles-by-zone/', views.get_vehicles_by_zone, name='get_vehicles_by_zone'),
    path('api/get-vehicle-logbook/', views.get_vehicle_logbook, name='get_vehicle_logbook'),

    # =========================================================
    # TINYMCE RICH TEXT EDITOR URL
    # =========================================================
    path('tinymce/', include('tinymce.urls')),
]