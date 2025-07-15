from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.validators import FileExtensionValidator


class TranscriptModel(models.Model):
    youtube_video_id = models.CharField(max_length=20, unique=True, db_index=True)
    language = models.CharField(max_length=10, default='en')
    transcript_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    transcript_text = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Transcript for video ID {self.youtube_video_id}"



class CourseModel(models.Model):
    course_name = models.CharField(max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='courses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('course_name', 'user')

    def __str__(self):
        return self.course_name


class VideoModel(models.Model):
    video_title = models.CharField(max_length=255)
    video_url = models.URLField()
    youtube_video_id = models.CharField(max_length=20, db_index=True)  # ❌ REMOVE unique=True
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='videos', db_index=True)
    course = models.ForeignKey(CourseModel, on_delete=models.CASCADE, related_name='videos', null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_accessed_at']
        unique_together = ('user', 'youtube_video_id')

    def __str__(self):
        return self.video_title



class SessionModel(models.Model):
    video = models.ForeignKey(VideoModel, on_delete=models.CASCADE, related_name='sessions', db_index=True)
    user = models.ForeignKey( settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(auto_now=True)
    total_watch_time = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('video', 'user')
        ordering = ['-last_accessed_at']

    def update_watch_time(self, seconds):
        self.total_watch_time += seconds
        self.save()


class NotesModel(models.Model):
    notes = models.TextField()
    time_stamp = models.FloatField(validators=[MinValueValidator(0)])
    session = models.ForeignKey(SessionModel, on_delete=models.CASCADE, related_name='notes', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['time_stamp']


class ImageModel(models.Model):
    image = models.ImageField(upload_to='clips/%Y/%m/%d/', validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])])
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    time_stamp = models.FloatField(validators=[MinValueValidator(0)])
    session = models.ForeignKey(SessionModel,on_delete=models.CASCADE,related_name='images', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['time_stamp']

class QAModel(models.Model):
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    time_stamp = models.FloatField(validators=[MinValueValidator(0)])
    session = models.ForeignKey(SessionModel, on_delete=models.CASCADE,related_name='qas', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['time_stamp']


class BookmarkModel(models.Model):
    time_stamp = models.FloatField(validators=[MinValueValidator(0)])
    session = models.ForeignKey(SessionModel,on_delete=models.CASCADE,related_name='bookmarks', db_index=True)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['time_stamp']
        unique_together = ('session', 'time_stamp')
    def __str__(self):
        return f"Bookmark at {self.time_stamp}s for session {self.session.id}"

