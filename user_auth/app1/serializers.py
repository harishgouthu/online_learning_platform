from rest_framework import serializers
from .models import CourseModel, VideoModel, SessionModel, NotesModel, ImageModel, QAModel, BookmarkModel
from django.core.validators import FileExtensionValidator
from rest_framework.exceptions import ValidationError
import re

# serializers.py
from rest_framework import serializers
import re


class TimestampField(serializers.Field):
    """
    Handles ALL timestamp formats:
    - Float seconds (90.5)
    - MM:SS, HH:MM:SS ("1:30", "1:30:45")
    - Human-readable ("1h30m45s")
    - Localized decimals ("1:30,5" → 90.5)
    """

    def to_internal_value(self, data):
        try:
            # Normalize input (handle commas, whitespace)
            timestamp_str = str(data).strip().replace(',', '.')

            # Reject negatives
            if '-' in timestamp_str:
                raise ValueError("Negative timestamps invalid")

            # Parse human-readable (1h30m45s)
            match = re.match(r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$', timestamp_str, re.IGNORECASE)
            if match and any(match.groups()):
                hours = int(match.group(1)) if match.group(1) else 0
                minutes = int(match.group(2)) if match.group(2) else 0
                seconds = float(match.group(3)) if match.group(3) else 0.0
                return hours * 3600 + minutes * 60 + seconds

            # Parse colon formats (MM:SS, HH:MM:SS)
            if ':' in timestamp_str:
                parts = list(map(float, timestamp_str.split(':')))
                if len(parts) == 2:  # MM:SS
                    return parts[0] * 60 + parts[1]
                elif len(parts) == 3:  # HH:MM:SS
                    return parts[0] * 3600 + parts[1] * 60 + parts[2]

            # Fallback to float
            return float(timestamp_str)
        except (ValueError, TypeError, AttributeError) as e:
            raise serializers.ValidationError(
                f"Invalid timestamp. Use seconds, MM:SS, HH:MM:SS, or 1h30m30s. Error: {str(e)}"
            )

class YoutubeSerializer(serializers.Serializer):
    youtube_video_url = serializers.URLField()
    question = serializers.CharField()
    time_stamp = TimestampField()
class CreateNoteSerializer(serializers.Serializer):
    youtube_video_url = serializers.URLField()
    notes = serializers.CharField()
    time_stamp = TimestampField()
class CreateSessionSerializer(serializers.Serializer):
    youtube_video_url = serializers.URLField()
class ImageUploadSerializer(serializers.Serializer):
    youtube_video_url = serializers.URLField()
    question = serializers.CharField(required=False, default="")
    time_stamp = TimestampField()
    image = serializers.ImageField()

    def validate_image(self, value):
        """Validate image file"""
        if value.size > 5 * 1024 * 1024:  # 5MB limit
            raise serializers.ValidationError("Image size cannot exceed 5MB")
        return value


class CourseModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModel
        fields = ['id', 'course_name', 'user', 'created_at', 'updated_at', 'is_active']

    def validate(self, attrs):
        user = attrs.get('user')
        course_name = attrs.get('course_name')

        if CourseModel.objects.filter(user=user, course_name__iexact=course_name).exists():
            raise serializers.ValidationError("You already have a course with this name.")

        return attrs




# class AskQuestionSerializer(serializers.Serializer):
#     youtube_video_url = serializers.URLField()
#     question = serializers.CharField()
#     time_stamp = serializers.FloatField()




class QASerializer(serializers.ModelSerializer):
    class Meta:
        model = QAModel
        fields = ['id', 'question', 'answer', 'time_stamp', 'created_at']

class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoModel
        fields = ['id','course', 'video_title', 'video_url', 'youtube_video_id', 'duration_seconds', 'created_at',  'last_accessed_at']
        read_only_fields = ['created_at', 'last_accessed_at']

class SessionSerializer(serializers.ModelSerializer):
    video = VideoSerializer()
    qas = QASerializer(many=True, read_only=True)

    class Meta:
        model = SessionModel
        fields = ['id', 'video', 'created_at', 'last_accessed_at', 'total_watch_time', 'is_active', 'qas']


class allusersSessionSerializer(serializers.ModelSerializer):
    video = VideoSerializer()
    qas = QASerializer(many=True, read_only=True)

    class Meta:
        model = SessionModel
        fields = ['id', 'video', 'created_at', 'last_accessed_at', 'total_watch_time', 'is_active', 'qas']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if self.context.get('exclude_user', False):
            # Remove user data if requested
            representation.pop('user', None)
        return representation



class ImageModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageModel
        fields = ['id', 'image', 'question', 'answer', 'time_stamp', 'created_at']


class SessionModelSerializer(serializers.ModelSerializer):
    video = VideoSerializer()
    images = ImageModelSerializer(many=True, read_only=True)
    class Meta:
        model = SessionModel
        fields = ['id', 'video', 'created_at', 'last_accessed_at', 'total_watch_time', 'is_active', 'images']


# serializers.py
# class CreateNoteSerializer(serializers.Serializer):
#     youtube_video_url = serializers.URLField()
#     notes = serializers.CharField()
#     time_stamp = serializers.FloatField()



class NotesModelSerializer(serializers.ModelSerializer):

    class Meta:
        model = NotesModel
        fields = ['id', 'session','notes', 'time_stamp', 'created_at']

class NotesSessionModelSerializer(serializers.ModelSerializer):
    video = VideoSerializer()
    notes = NotesModelSerializer(many=True, read_only=True)
    class Meta:
        model = SessionModel
        fields = ['id', 'video', 'created_at', 'video', 'last_accessed_at', 'total_watch_time', 'is_active',  'notes']



class VideoCourseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoModel
        fields = ['course']

    def validate_course(self, value):
        # Check if the course belongs to the authenticated user
        if value.user != self.context['request'].user:
            raise serializers.ValidationError("You don't own this course.")
        return value