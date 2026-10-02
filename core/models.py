from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from tinymce.models import HTMLField  # TinyMCE Rich Text Editor

# =========================================================
# ROLE MODEL
# =========================================================
class Role(models.Model):
    CATEGORY_CHOICES = (
        ('CEO', 'CEO'),
        ('PS', 'Personal Secretary'),
        ('GM', 'General Manager'),
        ('Manager', 'Manager'),
        ('ZM', 'Zonal Manager'),
        ('AM', 'Assistant Manager'),
        ('HR', 'HR'),
        ('Officer', 'Officer'),
        ('CFO', 'Chief Financial Officer'),
        ('Auditor', 'Auditor'),
        ('Other', 'Other'),
    )

    code = models.CharField("Designation", max_length=50, unique=True)
    name = models.CharField("Full Name", max_length=150)
    category = models.CharField(
        "Category",
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='Manager'
    )
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_role",
        verbose_name="User Name"
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.code or self.name

    def full_display(self):
        if self.code and self.code != self.name:
            return f"{self.code} ({self.name})"
        return self.name


    def __eq__(self, other):
        if isinstance(other, str):
            return self.code == other or self.category == other or self.name == other
        return super().__eq__(other)

    def __hash__(self):
        return super().__hash__()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.user:
            profile, _ = Profile.objects.get_or_create(user=self.user)
            if profile.role != self:
                profile.role = self
                profile.save()


# =========================================================
# ZONE MODEL
# =========================================================
class Zone(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="e.g., Head Office, Zone-A, Zone-B")
    title = models.CharField(max_length=200, default="WATER AND SANITATION SERVICES PESHAWAR", help_text="Main title on letterhead")
    subtitle = models.CharField(max_length=255, default="WATER AND SANITATION SERVICES PESHAWAR", help_text="Subtitle on letterhead (2nd line)")
    province = models.CharField(max_length=255, default="GOVERNMENT OF KHYBER PAKHTUNKHWA", blank=True, help_text="Province line on letterhead (e.g., Government of Khyber Pakhtunkhwa)")
    address = models.CharField(max_length=255, default="Plot # 33, Street No. 13, Sector E-8, Phase-VII, Hayatabad", blank=True, help_text="Address on letterhead")
    phone = models.CharField(max_length=100, blank=True, null=True, help_text="Phone number for the letterhead")
    logo_left = models.ImageField(upload_to='zone_logos/', blank=True, null=True, help_text="Left logo (defaults to WSSP logo if empty)")
    logo_right = models.ImageField(upload_to='zone_logos/', blank=True, null=True, help_text="Right logo (defaults to KPK Emblem if empty)")

    class Meta:
        ordering = ['name']
        verbose_name = 'Zone'
        verbose_name_plural = 'Zones'

    def __str__(self):
        return self.name

# =========================================================
# PROFILE MODEL
# =========================================================
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles")
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    department = models.CharField(max_length=100, blank=True, null=True)
    signature = models.ImageField(upload_to='signatures/', blank=True, null=True)

    def get_role_display(self):
        return str(self.role) if self.role else ""

    def get_role_with_department(self):
        return str(self.role) if self.role else (self.department or "")

    def __str__(self):
        return f"{self.user.username} ({self.get_role_with_department()})"

# Automatic Profile Creation Signal
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def auto_create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


# =========================================================
# COMMITMENT MODEL
# =========================================================
class Commitment(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    priority = models.CharField(
        max_length=20,
        choices=(('Normal', 'Normal'), ('High', 'High')),
        default='Normal'
    )
    category = models.CharField(
        max_length=50,
        choices=(
            ('Meeting', 'Meeting'),
            ('Visit', 'Visit'),
            ('Event', 'Event'),
        ),
        default='Meeting'
    )
    commitment_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='commitments_created')
    
    invited_managers = models.ManyToManyField(
        User,
        related_name="invited_commitments",
        blank=True,
        limit_choices_to=models.Q(profile__role__category='Manager') | models.Q(profile__role__code='Manager')
    )
    
    is_sent_to_manager = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_expired(self):
        if self.commitment_date:
            return self.commitment_date < timezone.now()
        return False

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.created_by.user.username}"

    def save(self, *args, **kwargs):
        if self.status == 'Approved':
            self.is_sent_to_manager = True
        super().save(*args, **kwargs)

# =========================================================
# FILE / FOLDER MODEL
# =========================================================
class File(models.Model):
    file_name = models.CharField(max_length=255)
    file_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.file_name

# =========================================================
# TASK MODEL (Cleaned & Updated)
# =========================================================
class Task(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Seen', 'Seen'),
        ('Completed', 'Completed'),
    )
    
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    title = models.CharField(max_length=200) 
    description = models.TextField(blank=True, null=True) 
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tasks_assigned")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks_received")
    current_handler_role = models.CharField(max_length=50, default="Manager") 
    due_date = models.DateField(blank=True, null=True) 
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    is_seen = models.BooleanField(default=False)
    seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} (From: {self.assigned_by.username} -> To: {self.assigned_to.username if self.assigned_to else 'Unassigned'})"

    @property
    def current_holder(self):
        return self.assigned_to

    @property
    def created_by(self):
        return self.assigned_by

    @property
    def updated_at(self):
        return self.created_at

# =========================================================
# REMARK / TASK FEEDBACK MODEL
# =========================================================
class Remark(models.Model):
    ACTION_CHOICES = (
        ('save', 'Submitted'),
        ('forward', 'Forwarded'),
        ('reverse', 'Reversed'),
        ('approve', 'Final Approved'),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='remarks')
    manager = models.ForeignKey(User, on_delete=models.CASCADE, related_name='remarks_given')
    feedback = models.TextField()
    addressed_to = models.CharField(max_length=255, blank=True, null=True) 
    action_taken = models.CharField(max_length=20, choices=ACTION_CHOICES, default='save')
    attachment_1 = models.FileField(upload_to='remark_attachments/', null=True, blank=True)
    attachment_2 = models.FileField(upload_to='remark_attachments/', null=True, blank=True)
    attachment_3 = models.FileField(upload_to='remark_attachments/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Remark by {self.manager.username} on Task '{self.task.title}'"

    def get_formatted_time(self):
        return self.created_at.strftime("%d %b %Y | %I:%M %p") 


class RemarkAttachment(models.Model):
    remark = models.ForeignKey(Remark, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='remark_attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for Remark {self.remark.id} ({self.file.name})"

# =========================================================
# TASK TRACKING / MOVEMENT LOG
# =========================================================
class TaskTracking(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='tracking_history')
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_history')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_history')
    message = models.CharField(max_length=255) 
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp'] 

    def __str__(self):
        return f"{self.task.title} moved to {self.to_user.username}"

# =========================================================
# NOTESHEET MODEL
# =========================================================
class Notesheet(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('In Progress', 'Seen'),
        ('Returned', 'Returned'),
        ('Completed', 'Completed'),
    )

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='notesheets', null=True, blank=True)
    title = models.CharField(max_length=200, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_notesheets")
    current_holder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notesheets_in_hand")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending", db_index=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    is_seen = models.BooleanField(default=False)
    seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        holder = self.current_holder.username if self.current_holder else "Unassigned"
        return f"{self.title} - Currently with {holder}"

# =========================================================
# NOTESHEET FORWARD MODEL
# =========================================================
class NotesheetForward(models.Model):
    notesheet = models.ForeignKey(Notesheet, on_delete=models.CASCADE, related_name="forwards")
    forwarded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notesheets_forwarded")
    forwarded_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notesheets_received")  
    remark = models.TextField(blank=True)
    attachment_1 = models.FileField(upload_to='notesheet_forwards/', null=True, blank=True)
    attachment_2 = models.FileField(upload_to='notesheet_forwards/', null=True, blank=True)
    attachment_3 = models.FileField(upload_to='notesheet_forwards/', null=True, blank=True)
    forwarded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-forwarded_at']

    def __str__(self):
        return f"{self.notesheet.title} → {self.forwarded_by} to {self.forwarded_to}"

# =========================================================
# NOTESHEET AGENDA MODEL
# =========================================================
class NotesheetAgenda(models.Model):
    notesheet = models.ForeignKey(Notesheet, on_delete=models.CASCADE, related_name="agendas")
    agenda_title = HTMLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Notesheet Agenda"
        verbose_name_plural = "Notesheet Agendas"

    def __str__(self):
        return f"Agenda #{self.id} - {self.notesheet.title}"

# =========================================================
# USER HIERARCHY MODEL
# =========================================================
class UserHierarchy(models.Model):
    boss = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='hierarchy_boss',
        verbose_name="User",
        help_text="Select the user for whom you are configuring the forwarding lists."
    )
    
    # Forwarding Lists
    requisition_subs = models.ManyToManyField(User, blank=True, related_name='req_bosses', verbose_name="Requisition Form List")
    notesheet_subs = models.ManyToManyField(User, blank=True, related_name='notesheet_bosses', verbose_name="Notesheet List")
    task_subs = models.ManyToManyField(User, blank=True, related_name='task_bosses', verbose_name="Task List")
    letter_subs = models.ManyToManyField(User, blank=True, related_name='letter_bosses', verbose_name="Letter List")

    def __str__(self):
        return f"User: {self.boss.username}"

    class Meta:
        verbose_name = "User Hierarchy"
        verbose_name_plural = "User Hierarchies"

# =====================================================================
# NOTESHEET ATTACHMENTS MODEL
# =====================================================================
class NotesheetAttachment(models.Model):
    notesheet = models.ForeignKey(
        'Notesheet', 
        on_delete=models.CASCADE, 
        related_name='attachments'
    )
    file = models.FileField(upload_to="notesheet_attachments/")
    flag_name = models.CharField(max_length=10, blank=True, null=True, help_text="e.g., 'A', 'B', 'C'")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        flag_label = self.flag_name if self.flag_name else "No Flag"
        return f"[{flag_label}] Attachment for Notesheet #{self.notesheet.id} - {self.file.name}"

# =====================================================================
# NOTESHEET RETURN TRACKING
# =====================================================================
class NotesheetReturn(models.Model):
    notesheet = models.ForeignKey(
        Notesheet, 
        on_delete=models.CASCADE, 
        related_name="returns"
    )
    returned_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="notesheets_returned_by_me"
    )
    returned_to = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="notesheets_returned_to_me"
    )  
    remark = models.TextField(blank=True)
    attachment_1 = models.FileField(upload_to='notesheet_returns/', null=True, blank=True)
    attachment_2 = models.FileField(upload_to='notesheet_returns/', null=True, blank=True)
    attachment_3 = models.FileField(upload_to='notesheet_returns/', null=True, blank=True)
    returned_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-returned_at']
        verbose_name = "Notesheet Return"
        verbose_name_plural = "Notesheet Returns"

    def __str__(self):
        return f"Return: {self.notesheet.title} ← From {self.returned_by.username} to {self.returned_to.username}"



# =========================================================
# LETTER SYSTEM MODELS
# =========================================================
class LetterFile(models.Model):
    file_title = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='letter_files')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Letter File"
        verbose_name_plural = "Letter Files"

    def __str__(self):
        return f"{self.reference_number} - {self.file_title}"


class Letter(models.Model):
    letter_file = models.ForeignKey(LetterFile, on_delete=models.CASCADE, related_name='letters')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_letters')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_letters')
    
    ref_no = models.CharField(max_length=100, blank=True, null=True)
    recipient_address = models.TextField(blank=True, null=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    signer_name = models.CharField(max_length=100, blank=True, null=True)
    signer_designation = models.CharField(max_length=100, blank=True, null=True)
    cc_list = models.TextField(blank=True, null=True)
    
    attachment = models.FileField(upload_to='letter_attachments/', blank=True, null=True)
    is_read = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Reply Fields
    reply_text = models.TextField(blank=True, null=True)
    reply_attachment = models.FileField(upload_to='letter_replies/', blank=True, null=True)
    reply_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} (From: {self.sender.username} -> To: {self.receiver.username})"


class DraftLetter(Letter):
    class Meta:
        proxy = True
        verbose_name = "Draft Letter"
        verbose_name_plural = "Draft Letters"



class LetterReplyAttachment(models.Model):
    letter = models.ForeignKey(Letter, on_delete=models.CASCADE, related_name='reply_attachments')
    file = models.FileField(upload_to='letter_reply_attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply Attachment for Letter {self.letter.id} ({self.file.name})"

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('notesheet', 'Notesheet'),
        ('task', 'Task'),
        ('commitment', 'Commitment'),
        ('letter', 'Letter'),
    )
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='notesheet')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient.username} - {self.title}"

# =====================================================================
# VEHICLE REQUISITION
# =====================================================================
class VehicleRequisition(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Completed', 'Completed'),
    )
    fleet_officer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requisitions_created')
    zone = models.CharField(max_length=100, blank=True, null=True)
    uc_route = models.CharField(max_length=100, blank=True, null=True)
    vehicle_number = models.CharField(max_length=50)
    issue_description = models.TextField()
    previous_issue_date = models.DateField(blank=True, null=True)
    estimated_cost = models.CharField(max_length=50, blank=True, null=True)
    driver_name = models.CharField(max_length=100)
    driver_mobile = models.CharField(max_length=20, blank=True, null=True)
    driver_cnic = models.CharField(max_length=20, blank=True, null=True)
    driver_signature = models.ImageField(upload_to='requisition_signatures/', blank=True, null=True)
    fleet_officer_signature = models.ImageField(upload_to='requisition_signatures/', blank=True, null=True)
    is_first_time = models.BooleanField(default=False, verbose_name="First time occurrence")
    fleet_officer_remarks = models.TextField(blank=True, null=True, verbose_name="Fleet Officer Remarks")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    manager_admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requisitions_received')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vehicle_number} - {self.driver_name}"


# =====================================================================
# VEHICLE REQUISITION ATTACHMENT
# =====================================================================
class VehicleRequisitionAttachment(models.Model):
    requisition = models.ForeignKey(
        VehicleRequisition,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='requisition_attachments/')
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for Requisition #{self.requisition.id} - {self.original_name}"

    @property
    def file_extension(self):
        import os
        _, ext = os.path.splitext(self.original_name)
        return ext.lower().lstrip('.')

    @property
    def is_image(self):
        return self.file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg']

    @property
    def is_pdf(self):
        return self.file_extension == 'pdf'

    class Meta:
        ordering = ['uploaded_at']

# =====================================================================
# VEHICLE REQUISITION FORWARD
# =====================================================================
class VehicleRequisitionForward(models.Model):
    requisition = models.ForeignKey(
        VehicleRequisition,
        on_delete=models.CASCADE,
        related_name='forwards'
    )
    forwarded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reqs_forwarded")
    forwarded_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reqs_received_forwards")  
    remark = models.TextField(blank=True)
    status_at_forward = models.CharField(max_length=20, blank=True, default='Pending')
    forwarded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Attachments (only for fleet officers - fzoned users)
    attachment_1 = models.FileField(upload_to='requisition_remark_attachments/', blank=True, null=True)
    attachment_2 = models.FileField(upload_to='requisition_remark_attachments/', blank=True, null=True)
    attachment_3 = models.FileField(upload_to='requisition_remark_attachments/', blank=True, null=True)
    attachment_4 = models.FileField(upload_to='requisition_remark_attachments/', blank=True, null=True)
    attachment_5 = models.FileField(upload_to='requisition_remark_attachments/', blank=True, null=True)
    is_fleet_officer_remark = models.BooleanField(default=False)

    class Meta:
        ordering = ['-forwarded_at']

    def __str__(self):
        return f"{self.requisition.vehicle_number} → {self.forwarded_by} to {self.forwarded_to}"