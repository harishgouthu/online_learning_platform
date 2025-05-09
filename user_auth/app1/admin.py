from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CourseModel, VideoModel, SessionModel,
    NotesModel, ImageModel, QAModel, BookmarkModel
)

class CourseModelAdmin(admin.ModelAdmin):
    list_display = ('course_name', 'user', 'created_at', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('course_name', 'user__username')
    raw_id_fields = ('user',)
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

class VideoModelAdmin(admin.ModelAdmin):
    list_display = ('video_title', 'youtube_id_link', 'user', 'duration_formatted', 'last_accessed_at')  # Changed last_accessed to last_accessed_at
    list_filter = ('created_at', 'course')
    search_fields = ('video_title', 'youtube_video_id', 'user__username')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'last_accessed_at', 'youtube_thumbnail_preview')
    date_hierarchy = 'created_at'

    def youtube_id_link(self, obj):
        return format_html(
            '<a href="{}" target="_blank">{}</a>',
            obj.video_url,
            obj.youtube_video_id
        )
    youtube_id_link.short_description = "YouTube ID"

    def duration_formatted(self, obj):
        if obj.duration_seconds:
            minutes, seconds = divmod(obj.duration_seconds, 60)
            return f"{minutes}m {seconds}s"
        return "-"
    duration_formatted.short_description = "Duration"

    def youtube_thumbnail_preview(self, obj):
        if obj.thumbnail_url:
            return format_html(
                '<img src="{}" style="max-height: 100px;" />',
                obj.thumbnail_url
            )
        return "-"
    youtube_thumbnail_preview.short_description = "Thumbnail Preview"
class SessionModelAdmin(admin.ModelAdmin):
    list_display = ('video_title', 'user', 'created_at', 'watch_time_formatted', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('video__video_title', 'user__username')
    raw_id_fields = ('video', 'user')
    readonly_fields = ('created_at', 'last_accessed_at', 'watch_time_formatted')
    date_hierarchy = 'created_at'

    def video_title(self, obj):
        return obj.video.video_title
    video_title.short_description = "Video"

    def watch_time_formatted(self, obj):
        hours, remainder = divmod(obj.total_watch_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"
    watch_time_formatted.short_description = "Watch Time"

class NotesModelAdmin(admin.ModelAdmin):
    list_display = ('truncated_notes', 'session_info', 'time_stamp_formatted', 'created_at')
    search_fields = ('notes', 'session__video__video_title')
    raw_id_fields = ('session',)
    readonly_fields = ('created_at', 'updated_at')

    def session_info(self, obj):
        return f"{obj.session.user.username} - {obj.session.video.video_title}"
    session_info.short_description = "Session"

    def time_stamp_formatted(self, obj):
        minutes, seconds = divmod(obj.time_stamp, 60)
        return f"{int(minutes)}:{int(seconds):02d}"
    time_stamp_formatted.short_description = "Timestamp"

    def truncated_notes(self, obj):
        return obj.notes[:50] + '...' if len(obj.notes) > 50 else obj.notes
    truncated_notes.short_description = "Notes"

class ImageModelAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'truncated_question', 'session_info', 'time_stamp_formatted')
    search_fields = ('question', 'session__video__video_title')
    raw_id_fields = ('session',)
    readonly_fields = ('created_at', 'image_preview_large')
    list_per_page = 20

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px;" />',
                obj.image.url
            )
        return "-"
    image_preview.short_description = "Preview"

    def image_preview_large(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 300px;" />',
                obj.image.url
            )
        return "-"
    image_preview_large.short_description = "Large Preview"

    def session_info(self, obj):
        return f"{obj.session.user.username} - {obj.session.video.video_title}"
    session_info.short_description = "Session"

    def time_stamp_formatted(self, obj):
        minutes, seconds = divmod(obj.time_stamp, 60)
        return f"{int(minutes)}:{int(seconds):02d}"
    time_stamp_formatted.short_description = "Timestamp"

    def truncated_question(self, obj):
        return obj.question[:50] + '...' if len(obj.question) > 50 else obj.question
    truncated_question.short_description = "Question"

class QAModelAdmin(admin.ModelAdmin):
    list_display = ('truncated_question', 'truncated_answer', 'session_info', 'time_stamp_formatted')
    search_fields = ('question', 'answer', 'session__video__video_title')
    raw_id_fields = ('session',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 30

    def session_info(self, obj):
        return f"{obj.session.user.username} - {obj.session.video.video_title}"
    session_info.short_description = "Session"

    def time_stamp_formatted(self, obj):
        minutes, seconds = divmod(obj.time_stamp, 60)
        return f"{int(minutes)}:{int(seconds):02d}"
    time_stamp_formatted.short_description = "Timestamp"

    def truncated_question(self, obj):
        return obj.question[:50] + '...' if len(obj.question) > 50 else obj.question
    truncated_question.short_description = "Question"

    def truncated_answer(self, obj):
        return obj.answer[:50] + '...' if obj.answer and len(obj.answer) > 50 else (obj.answer or "-")
    truncated_answer.short_description = "Answer"

class BookmarkModelAdmin(admin.ModelAdmin):
    list_display = ('time_stamp_formatted', 'truncated_note', 'session_info', 'created_at')
    search_fields = ('note', 'session__video__video_title')
    raw_id_fields = ('session',)
    readonly_fields = ('created_at',)
    list_filter = ('created_at',)

    def session_info(self, obj):
        return f"{obj.session.user.username} - {obj.session.video.video_title}"
    session_info.short_description = "Session"

    def time_stamp_formatted(self, obj):
        minutes, seconds = divmod(obj.time_stamp, 60)
        return f"{int(minutes)}:{int(seconds):02d}"
    time_stamp_formatted.short_description = "Timestamp"

    def truncated_note(self, obj):
        return obj.note[:50] + '...' if obj.note and len(obj.note) > 50 else (obj.note or "-")
    truncated_note.short_description = "Note"

admin.site.register(CourseModel, CourseModelAdmin)
admin.site.register(VideoModel, VideoModelAdmin)
admin.site.register(SessionModel, SessionModelAdmin)
admin.site.register(NotesModel, NotesModelAdmin)
admin.site.register(ImageModel, ImageModelAdmin)
admin.site.register(QAModel, QAModelAdmin)
admin.site.register(BookmarkModel, BookmarkModelAdmin)