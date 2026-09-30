from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.models import User
from .models import (
    Role, Profile, Commitment, Task, Remark, 
    File, Notesheet, NotesheetForward, NotesheetAgenda,
    UserHierarchy, NotesheetReturn, NotesheetAttachment,
    LetterFile, Letter, DraftLetter, Notification, VehicleRequisition,
    VehicleRequisitionAttachment,
    Zone
)

# =========================================================
# 📂 FILE / FOLDER ADMIN
# =========================================================

@admin.register(NotesheetAttachment)
class NotesheetAttachmentAdmin(admin.ModelAdmin):
    list_display = ('notesheet', 'uploaded_at')


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'file_number', 'created_at')
    search_fields = ('file_name', 'file_number')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

# =========================================================
# 🌍 ZONE ADMIN
# =========================================================
@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'subtitle', 'province', 'phone')
    search_fields = ('name', 'title', 'subtitle', 'province', 'address')

# =========================================================
# 🏷️ ROLE ADMIN
# =========================================================
class RoleAdminForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'user' in self.fields:
            self.fields['user'].queryset = User.objects.order_by('first_name', 'last_name', 'username')
            self.fields['user'].label_from_instance = lambda obj: (
                f"{obj.get_full_name()} ({obj.username})" if obj.get_full_name().strip() else obj.username
            )
            self.fields['user'].label = "User Name"

            import json
            from django.utils.safestring import mark_safe

            users_dict = {
                str(u.id): {
                    'username': u.username,
                    'full_name': u.get_full_name().strip() or u.username
                }
                for u in User.objects.all()
            }
            users_json = json.dumps(users_dict)

            js_script = mark_safe(f"""
            <span style="display:block; font-size:12px; color:#9ca3af; margin-top:4px;">
              Select the assigned user. Dropdown displays <strong>Full Name (username)</strong>.
            </span>
            <script>
            (function() {{
                var userData = {users_json};
                function attachAutoFill() {{
                    var userSelect = document.getElementById('id_user');
                    var codeInput = document.getElementById('id_code');
                    var nameInput = document.getElementById('id_name');
                    if (userSelect) {{
                        userSelect.addEventListener('change', function() {{
                            var uid = this.value;
                            if (uid && userData[uid]) {{
                                if (codeInput && !codeInput.value) {{
                                    codeInput.value = userData[uid].username;
                                }}
                                if (nameInput && !nameInput.value) {{
                                    nameInput.value = userData[uid].full_name;
                                }}
                            }}
                        }});
                    }}
                }}
                if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', attachAutoFill);
                }} else {{
                    attachAutoFill();
                }}
            }})();
            </script>
            """)
            self.fields['user'].help_text = js_script



@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    form = RoleAdminForm
    fields = ('code', 'name', 'category', 'user')
    list_display = ('code', 'name', 'category', 'get_assigned_users')
    list_filter = ('category',)
    search_fields = ('code', 'name', 'category', 'user__first_name', 'user__last_name', 'user__username')
    ordering = ('category', 'code')

    def get_assigned_users(self, obj):
        u = obj.user or (obj.profiles.first().user if obj.profiles.exists() else None)
        if u:
            full_name = u.get_full_name().strip()
            display = full_name if full_name else u.username
            return format_html('<span style="color: #059669; font-weight: 700; font-size: 13px;">{}</span>', display)
        return format_html('<span style="color: #9ca3af; font-style: italic;">Unassigned</span>')
    get_assigned_users.short_description = 'Assigned Person / User Name'


# =========================================================
# 👤 PROFILE ADMIN — Dual Signature Widget (Draw + Upload)
# =========================================================
import base64
import uuid
from django import forms
from django.core.files.base import ContentFile
from django.utils.safestring import mark_safe


class SignaturePadWidget(forms.Widget):
    """Custom admin widget: draw on canvas OR upload image file."""
    needs_multipart_form = True

    def render(self, name, value, attrs=None, renderer=None):
        current_html = ''
        if value and hasattr(value, 'url'):
            current_html = (
                '<div style="margin-bottom:12px;">'
                '<p style="font-size:12px;color:#6b7280;margin:0 0 6px;">Current saved signature:</p>'
                f'<img src="{value.url}" style="max-height:90px;border:1px solid #059669;'
                'padding:6px;background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(5,150,105,.15);">'
                '</div>'
            )

        widget_id = (attrs or {}).get('id', f'id_{name}')

        html = f'''
<div style="font-family:Segoe UI,sans-serif;max-width:560px;">

  <!-- TAB SWITCHER -->
  <div style="display:flex;margin-bottom:0;border:1.5px solid #059669;border-radius:10px 10px 0 0;overflow:hidden;">
    <button type="button" id="{widget_id}-tab-draw"
      onclick="sigTabSwitch('{widget_id}','draw')"
      style="flex:1;padding:9px 0;font-size:13px;font-weight:600;border:none;cursor:pointer;
             background:linear-gradient(135deg,#0d2b1e,#059669);color:#fff;transition:.2s;">
      &#9997;&#65039; Draw Signature
    </button>
    <button type="button" id="{widget_id}-tab-upload"
      onclick="sigTabSwitch('{widget_id}','upload')"
      style="flex:1;padding:9px 0;font-size:13px;font-weight:600;border:none;cursor:pointer;
             background:#f9fafb;color:#374151;border-left:1.5px solid #059669;transition:.2s;">
      &#128193; Upload Image
    </button>
  </div>

  <!-- DRAW PANEL -->
  <div id="{widget_id}-panel-draw"
       style="border:1.5px solid #059669;border-top:none;border-radius:0 0 10px 10px;padding:14px;background:#fafafa;">
    <canvas id="{widget_id}-canvas"
      style="width:100%;height:140px;background:#fff;border:1px dashed #a7f3d0;
             border-radius:8px;cursor:crosshair;display:block;"></canvas>
    <div style="display:flex;gap:8px;margin-top:10px;align-items:center;">
      <button type="button" onclick="sigClear('{widget_id}')"
        style="padding:6px 16px;border:1px solid #dc2626;color:#dc2626;background:#fff;
               border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">
        &#128465; Clear
      </button>
      <span id="{widget_id}-status" style="font-size:11px;color:#9ca3af;">Draw your signature using mouse or touch</span>
    </div>
  </div>

  <!-- UPLOAD PANEL (hidden by default) -->
  <div id="{widget_id}-panel-upload"
       style="display:none;border:1.5px solid #059669;border-top:none;border-radius:0 0 10px 10px;padding:14px;background:#fafafa;">
    {current_html}
    <input type="file" name="{name}_file" accept="image/*"
           style="font-size:13px;padding:6px;border:1px solid #d1d5db;border-radius:6px;width:100%;">
    <p style="font-size:11px;color:#9ca3af;margin:6px 0 0;">Accepted: PNG, JPG (transparent background preferred)</p>
  </div>

  <!-- Hidden: stores base64 drawn data -->
  <input type="hidden" name="{name}_drawn" id="{widget_id}-drawn">

</div>

<script src="https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js"></script>
<script>
(function() {{
  var wid = "{widget_id}";
  var canvas = document.getElementById(wid + "-canvas");
  if (!canvas) return;
  var sp = new SignaturePad(canvas, {{ penColor: "rgb(10,50,30)", minWidth: 1, maxWidth: 2.5 }});
  var drawn = document.getElementById(wid + "-drawn");
  var statusEl = document.getElementById(wid + "-status");

  function resize() {{
    var r = window.devicePixelRatio || 1;
    var d = sp.isEmpty() ? null : sp.toData();
    canvas.width  = canvas.offsetWidth  * r;
    canvas.height = canvas.offsetHeight * r;
    canvas.getContext("2d").scale(r, r);
    sp.clear();
    if (d) sp.fromData(d);
  }}
  setTimeout(resize, 120);
  window.addEventListener("resize", resize);

  function captureSignature() {{
    if (sp.isEmpty()) {{
      drawn.value = "";
      statusEl.textContent = "Draw your signature using mouse or touch";
      statusEl.style.color = "#9ca3af";
    }} else {{
      drawn.value = sp.toDataURL("image/png");
      statusEl.textContent = "✓ Signature captured — click Save to store it";
      statusEl.style.color = "#059669";
    }}
  }}

  // SignaturePad v4+ events
  sp.addEventListener("endStroke", captureSignature);
  canvas.addEventListener("mouseup", captureSignature);
  canvas.addEventListener("touchend", captureSignature);

  // Form submission fallback
  var form = canvas.closest('form');
  if (form) {{
    form.addEventListener('submit', function() {{
      if (document.getElementById(wid + "-panel-draw").style.display !== "none") {{
        captureSignature();
      }}
    }});
  }}

  window.sigPads = window.sigPads || {{}};
  window.sigPads[wid] = sp;

  window.sigClear = function(id) {{
    if (window.sigPads[id]) {{
      var pad = window.sigPads[id];
      var c = document.getElementById(id + "-canvas");
      if (c) {{
          var ctx = c.getContext("2d");
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          ctx.clearRect(0, 0, c.width, c.height);
          var r = window.devicePixelRatio || 1;
          ctx.scale(r, r);
      }}
      pad.clear();
    }}
    var d = document.getElementById(id + "-drawn");
    if (d) d.value = "";
    var s = document.getElementById(id + "-status");
    if (s) {{
      s.textContent = "Draw your signature using mouse or touch";
      s.style.color = "#9ca3af";
    }}
  }};

  window.sigTabSwitch = function(id, tab) {{
    var pd = document.getElementById(id + "-panel-draw");
    var pu = document.getElementById(id + "-panel-upload");
    var td = document.getElementById(id + "-tab-draw");
    var tu = document.getElementById(id + "-tab-upload");
    if (!pd || !pu || !td || !tu) return;

    if (tab === "draw") {{
      pd.style.display = ""; pu.style.display = "none";
      td.style.background = "linear-gradient(135deg,#0d2b1e,#059669)"; td.style.color = "#fff";
      tu.style.background = "#f9fafb"; tu.style.color = "#374151";
      if (window.sigPads[id]) {{
          // Slight delay to allow DOM to render before resizing canvas
          setTimeout(function() {{
              var canvas = document.getElementById(id + "-canvas");
              var sp = window.sigPads[id];
              var r = window.devicePixelRatio || 1;
              var d = sp.isEmpty() ? null : sp.toData();
              canvas.width  = canvas.offsetWidth  * r;
              canvas.height = canvas.offsetHeight * r;
              canvas.getContext("2d").scale(r, r);
              sp.clear();
              if (d) sp.fromData(d);
          }}, 50);
      }}
    }} else {{
      pd.style.display = "none"; pu.style.display = "";
      tu.style.background = "linear-gradient(135deg,#0d2b1e,#059669)"; tu.style.color = "#fff";
      td.style.background = "#f9fafb"; td.style.color = "#374151";
      var drawn = document.getElementById(id + "-drawn");
      if (drawn) drawn.value = "";
    }}
  }};
}})();
</script>
'''
        return mark_safe(html)

    def value_from_datadict(self, data, files, name):
        """
        Always return None so Django's FileField keeps the existing value.
        Actual saving is handled entirely in save_model.
        """
        return None

    def value_omitted_from_data(self, data, files, name):
        """
        Return True so Django skips form processing for this field
        and never touches the existing signature value.
        All saving is done manually in ProfileAdmin.save_model().
        """
        return True


class ProfileAdminForm(forms.ModelForm):
    class Meta:
        from .models import Profile
        model = Profile
        fields = '__all__'
        widgets = {'signature': SignaturePadWidget()}


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    form = ProfileAdminForm

    list_display = ('user', 'role', 'zone', 'department', 'signature_preview')
    list_filter = ('role', 'zone', 'department')
    search_fields = ('user__username', 'department', 'user__first_name', 'user__last_name', 'zone__name')
    ordering = ('role', 'user__username')

    readonly_fields = ('signature_detail_preview',)
    fields = ('user', 'role', 'zone', 'department', 'signature', 'signature_detail_preview')

    def save_model(self, request, obj, form, change):
        """
        Save all non-signature fields first via super().
        Then handle signature separately: drawn canvas OR uploaded file.
        """
        # Step 1: Save all other profile fields normally
        super().save_model(request, obj, form, change)

        # Step 2: Handle uploaded file (Upload Image tab)
        from django.contrib import messages as msg
        sig_file = request.FILES.get('signature_file')
        if sig_file:
            try:
                filename = f'signatures/sig_upload_{obj.pk}_{uuid.uuid4().hex[:8]}.png'
                obj.signature.save(filename, sig_file, save=True)
                msg.success(request, '✅ Signature image uploaded and saved!')
            except Exception as e:
                msg.error(request, f'❌ Upload failed: {e}')
            return

        # Step 3: Handle drawn canvas signature (base64 PNG)
        from django.contrib import messages as msg
        drawn_data = request.POST.get('signature_drawn', '').strip()
        if drawn_data and drawn_data.startswith('data:image'):
            try:
                header, imgstr = drawn_data.split(';base64,')
                ext = (header.split('/')[-1] or 'png').split(';')[0]
                filename = f'signatures/sig_drawn_{obj.pk}_{uuid.uuid4().hex[:8]}.{ext}'
                decoded  = base64.b64decode(imgstr)
                content  = ContentFile(decoded, name=filename)
                obj.signature.save(filename, content, save=True)
                msg.success(request, f'✅ Drawn signature saved! ({len(decoded)} bytes)')
            except Exception as e:
                msg.error(request, f'❌ Drawn signature failed: {e}')
        else:
            preview = (drawn_data[:60] + '...') if len(drawn_data) > 60 else (drawn_data or '-- empty --')
            msg.warning(request, f'⚠️ No signature data received. signature_drawn="{preview}"')


    def signature_preview(self, obj):
        if obj.signature:
            return format_html(
                '<img src="{}" style="height:35px;width:auto;border:1px solid #059669;'
                'padding:2px;background:white;border-radius:4px;" />',
                obj.signature.url
            )
        return "No Signature"
    signature_preview.short_description = 'Signature'

    def signature_detail_preview(self, obj):
        if obj.signature:
            return format_html(
                '<div style="margin-top:5px;">'
                '<img src="{}" style="max-height:120px;width:auto;border:1px solid #059669;'
                'padding:6px;background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(5,150,105,.15);" />'
                '</div>',
                obj.signature.url
            )
        return "No Digital Signature Saved Yet"
    signature_detail_preview.short_description = 'Current Saved Signature'

# =========================================================
# 🤝 COMMITMENT ADMIN
# =========================================================
@admin.register(Commitment)
class CommitmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'commitment_date', 'status', 'priority', 'category')
    list_filter = ('status', 'priority', 'category', 'commitment_date')
    search_fields = ('title', 'description', 'location', 'created_by__user__username')
    date_hierarchy = 'commitment_date'
    ordering = ('-commitment_date',)
    readonly_fields = ('created_at', 'updated_at')


# =========================================================
# 📝 TASK ADMIN (NOTESHEET)
# =========================================================
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'file', 'assigned_by', 'current_handler_role', 'status', 'created_at')
    list_filter = ('status', 'current_handler_role', 'assigned_by', 'file')
    search_fields = ('title', 'description', 'assigned_by__username')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

# =========================================================
# 💬 REMARK ADMIN (NOTESHEET PARAS)
# =========================================================
@admin.register(Remark)
class RemarkAdmin(admin.ModelAdmin):
    list_display = ('task', 'manager', 'action_taken', 'created_at')
    list_filter = ('action_taken', 'created_at')
    search_fields = ('task__title', 'manager__username', 'feedback')

# =========================================================
# 🔹 NOTESHEET INLINES
# =========================================================
class NotesheetAgendaInline(admin.TabularInline):
    model = NotesheetAgenda
    extra = 1
    fields = ('agenda_title', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True

class NotesheetForwardInline(admin.TabularInline):
    model = NotesheetForward
    extra = 0
    fields = ('forwarded_by', 'forwarded_to', 'remark', 'forwarded_at')
    readonly_fields = ('forwarded_by', 'forwarded_to', 'remark', 'forwarded_at')
    can_delete = False
    show_change_link = True

class NotesheetReturnInline(admin.TabularInline):
    model = NotesheetReturn
    extra = 0
    fields = ('returned_by', 'returned_to', 'remark', 'returned_at')
    readonly_fields = ('returned_by', 'returned_to', 'remark', 'returned_at')
    can_delete = False
    show_change_link = True

# =========================================================
# 📄 MAIN NOTESHEET ADMIN
# =========================================================
@admin.register(Notesheet)
class NotesheetAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'current_holder', 'status',  'created_at')
    list_filter = ('status', 'due_date', 'created_at')
    search_fields = ('title',)
    autocomplete_fields = ('created_by', 'current_holder')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [NotesheetAgendaInline, NotesheetForwardInline, NotesheetReturnInline]
    ordering = ('-created_at',)

@admin.register(NotesheetForward)
class NotesheetForwardAdmin(admin.ModelAdmin):
    list_display = ('notesheet', 'forwarded_by', 'forwarded_to', 'forwarded_at')
    list_filter = ('forwarded_at',)
    search_fields = ('notesheet__title',)

@admin.register(NotesheetReturn)
class NotesheetReturnAdmin(admin.ModelAdmin):
    list_display = ('notesheet', 'returned_by', 'returned_to', 'returned_at')
    list_filter = ('returned_at',)
    search_fields = ('notesheet__title', 'remark')

@admin.register(NotesheetAgenda)
class NotesheetAgendaAdmin(admin.ModelAdmin):
    list_display = ('notesheet', 'agenda_preview', 'created_at')
    search_fields = ('notesheet__title',)
    readonly_fields = ('agenda_rendered', 'created_at')

    def agenda_preview(self, obj):
        import re
        plain = re.sub(r'<[^>]+>', '', obj.agenda_title or '')
        plain = plain.strip()
        return plain[:80] + '…' if len(plain) > 80 else plain
    agenda_preview.short_description = 'Agenda (Preview)'

    def agenda_rendered(self, obj):
        return format_html(obj.agenda_title or '')
    agenda_rendered.short_description = 'Agenda (Rendered)'

# =========================================================
# 👑 USER HIERARCHY ADMIN
# =========================================================
@admin.register(UserHierarchy)
class UserHierarchyAdmin(admin.ModelAdmin):
    list_display = ('boss',)
    search_fields = ('boss__username',)
    filter_horizontal = ('requisition_subs', 'notesheet_subs', 'task_subs', 'letter_subs')
    
    fieldsets = (
        ('User', {
            'fields': ('boss',)
        }),
        ('Requisition Form — Forwarding List', {
            'fields': ('requisition_subs',),
            'classes': ('collapse',),
            'description': 'Select users who should appear in the Requisition Form forwarding list for this user.'
        }),
        ('Notesheet — Forwarding List', {
            'fields': ('notesheet_subs',),
            'classes': ('collapse',),
            'description': 'Select users who should appear in the Notesheet forwarding list for this user.'
        }),
        ('Task — Forwarding List', {
            'fields': ('task_subs',),
            'classes': ('collapse',),
            'description': 'Select users who should appear in the Task forwarding list for this user.'
        }),
        ('Letter — Forwarding List', {
            'fields': ('letter_subs',),
            'classes': ('collapse',),
            'description': 'Select users who should appear in the Letter forwarding list for this user.'
        }),
    )

# =========================================================
# 📩 LETTER SYSTEM ADMINS (UPDATED & ENHANCED)
# =========================================================
@admin.register(LetterFile)
class LetterFileAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'file_title', 'created_by', 'created_at')
    search_fields = ('reference_number', 'file_title', 'created_by__username')
    list_filter = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = ('subject_preview', 'sender', 'receiver', 'letter_file', 'read_status', 'created_at')
    list_filter = ('is_read', 'created_at', 'letter_file')
    search_fields = ('subject', 'sender__username', 'receiver__username', 'letter_file__reference_number')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    def subject_preview(self, obj):
        """Shortens subject for clean table rendering."""
        return obj.subject[:60] + '...' if len(obj.subject) > 60 else obj.subject
    subject_preview.short_description = 'Subject'

    def read_status(self, obj):
        """Displays Read/Unread badge cleanly in admin."""
        if obj.is_read:
            return format_html('<span style="color: green; font-weight: bold;">✔ Read</span>')
        return format_html('<span style="color: red; font-weight: bold;">✖ Unread</span>')
    read_status.short_description = 'Status'


@admin.register(DraftLetter)
class DraftLetterAdmin(admin.ModelAdmin):
    list_display = ('subject_preview', 'sender', 'receiver', 'letter_file', 'created_at')
    list_filter = ('created_at', 'letter_file')
    search_fields = ('subject', 'sender__username', 'receiver__username', 'letter_file__reference_number')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_draft=True)

    def subject_preview(self, obj):
        return obj.subject[:60] + '...' if len(obj.subject) > 60 else obj.subject
    subject_preview.short_description = 'Subject'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'sender', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username', 'sender__username')
    ordering = ('-created_at',)

# =========================================================
# 🚚 VEHICLE REQUISITION ADMIN
# =========================================================
@admin.register(VehicleRequisition)
class VehicleRequisitionAdmin(admin.ModelAdmin):
    list_display = ('vehicle_number', 'driver_name', 'fleet_officer', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('vehicle_number', 'driver_name', 'fleet_officer__username')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(VehicleRequisitionAttachment)
class VehicleRequisitionAttachmentAdmin(admin.ModelAdmin):
    list_display = ('requisition', 'original_name', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('original_name', 'requisition__vehicle_number')
    ordering = ('-uploaded_at',)