
import io




from PIL import Image


import google.generativeai as genai

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.core.cache import cache
from rest_framework import status, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, UpdateAPIView

# from core.pagination import PreserveQueryParamsPagination
from .models import ImageModel, NotesModel, QAModel, SessionModel, VideoModel, CourseModel, TranscriptModel
from .serializers import (
    YoutubeSerializer,
    CreateNoteSerializer,
    ImageUploadSerializer,
    NotesSessionModelSerializer,
    SessionModelSerializer,
    SessionSerializer,
    allusersSessionSerializer,
    CourseModelSerializer,
    VideoCourseUpdateSerializer,
    VideoSerializer,
    CreateSessionSerializer,
    YoutubeTranscriptSerializer,
    TimestampField,
    ScreenshotRequestSerializer,
    MCQModelSerializer,
)
from .utils import check_question_limit,extract_youtube_video_id,get_video_title_with_cache,get_transcript_with_cache,get_transcript_languages_cached




class AskQuestionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        serializer = YoutubeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Invalid input data.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        video_url = serializer.validated_data['youtube_video_url']
        question = serializer.validated_data['question']
        time_stamp = int(serializer.validated_data['time_stamp'])

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_title = get_video_title_with_cache(video_id, settings.YOUTUBE_API_KEY)
        if not video_title:
            return Response({
                "success": False,
                "message": "Could not retrieve video title."
            }, status=status.HTTP_400_BAD_REQUEST)

        video, _ = VideoModel.objects.get_or_create(
            user=user,
            youtube_video_id=video_id,
            defaults={'video_title': video_title, 'video_url': video_url}
        )

        session, created = SessionModel.objects.get_or_create(user=user, video=video)
        session_status = "New session created" if created else "Session resumed"
        limit_exceeded, limit_message = check_question_limit(user, session)
        if limit_exceeded:
            return Response({
                "success": False,
                "message": limit_message,
                "is_premium": bool(user.is_premium)
            }, status=status.HTTP_403_FORBIDDEN)

        transcript_source = "model"
        transcript_obj = TranscriptModel.objects.filter(youtube_video_id=video_id).first()
        full_transcript = transcript_obj.transcript_data if transcript_obj else None

        if not full_transcript:
            transcript_data = get_transcript_with_cache(video_id)
            full_transcript = transcript_data.get("segments") if transcript_data else None

            if full_transcript:
                TranscriptModel.objects.create(
                    youtube_video_id=video_id,
                    language='en',
                    transcript_data=full_transcript,
                    transcript_text=transcript_data.get("full_text", "")
                )
                transcript_source = "fetched"

        available_lang_names = []
        if full_transcript:
            start_range = max(0, time_stamp - 60)
            end_range = time_stamp + 60

            transcript_segment = " ".join([
                entry['text'] for entry in full_transcript
                if start_range <= entry['start'] <= end_range
            ])

            if not transcript_segment.strip():
                return Response({
                    "success": False,
                    "message": "No transcript data found near the timestamp."
                }, status=status.HTTP_400_BAD_REQUEST)

            prompt = (
                f"You are a helpful assistant. Based only on the following segment of a YouTube video transcript, "
                f"which is from around timestamp {time_stamp} seconds, answer the user's question.\n\n"
                f"Transcript Segment:\n{transcript_segment}\n\n"
                f"Question: {question}\nAnswer:"
            )
        else:
            available_languages = get_transcript_languages_cached(video_id)
            available_lang_names = [lang["language_name"] for lang in available_languages]

            prompt = (
                f"You are a helpful assistant. The user has a question about a YouTube video, but no English transcript is available. "
                f"Based on the video title and context, do your best to help them.\n\n"
                f"Video Title: {video_title}\n"
                f"Video URL: {video_url}\n"
                f"Timestamp (seconds): {time_stamp}\n"
                f"User's Question: {question}\n\n"
                f"Answer:"
            )

        try:
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(prompt)
            answer = getattr(response, "text", "").strip()
            if not answer:
                return Response({
                    "success": False,
                    "message": "Gemini API did not return a valid response."
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({
                "success": False,
                "message": f"Gemini API failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        qa = QAModel.objects.create(
            session=session,
            question=question,
            answer=answer,
            time_stamp=time_stamp
        )

        return Response({
            "success": True,
            "message": "Q&A created successfully.",
            "data": {
                'id': qa.id,
                'question': qa.question,
                'answer': qa.answer,
                'transcript_segment': transcript_segment if full_transcript else "Transcript not available.",
                # 'full_transcript': full_transcript if full_transcript else None,
                # 'session': session.id,
                # 'session_status': session_status,
                # 'time_stamp': qa.time_stamp,
                # 'created_at': qa.created_at,
                # 'transcript_source': transcript_source,
                # 'available_transcript_languages': available_lang_names if not full_transcript else []
            }
        }, status=status.HTTP_201_CREATED)
    def get(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({
                "success": False,
                "message": "youtube_video_url is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SessionModel.objects.select_related('video').get(
                user=request.user,
                video__youtube_video_id=video_id
            )
        except SessionModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "Session not found for this video."
            }, status=status.HTTP_404_NOT_FOUND)

        qas = session.qas.all().order_by('time_stamp')

        qa_data = [
            {
                'id': qa.id,
                'question': qa.question,
                'answer': qa.answer,
                'time_stamp': qa.time_stamp,
                'created_at': qa.created_at,
                'updated_at': qa.updated_at
            } for qa in qas
        ]

        video_data = {
            'id': session.video.id,
            'title': session.video.video_title,
            'url': session.video.video_url,
            'youtube_video_id': session.video.youtube_video_id,
            'duration_seconds': session.video.duration_seconds,
            'created_at': session.video.created_at,
            'last_accessed_at': session.video.last_accessed_at
        }

        session_data = {
            'id': session.id,
            'total_watch_time': session.total_watch_time,
            'created_at': session.created_at,
            'last_accessed_at': session.last_accessed_at,
            'is_active': session.is_active
        }

        return Response({
            "success": True,
            "message": "Q&A data retrieved successfully.",
            "data": {
                'video': video_data,
                'session': session_data,
                'qa_list': qa_data
            }
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        qa_id = request.query_params.get('id')
        if not qa_id:
            return Response({
                "success": False,
                "message": "QA id is required to delete."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            qa = QAModel.objects.get(id=qa_id, session__user=request.user)
            qa.delete()
            return Response({
                "success": True,
                "message": "Q&A deleted successfully."
            }, status=status.HTTP_204_NO_CONTENT)
        except QAModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "Q&A not found or unauthorized."
            }, status=status.HTTP_404_NOT_FOUND)






class ClipTabAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def convert_png_to_jpeg(self, uploaded_file):
        """Convert PNG image to JPEG format for Gemini processing."""
        image = Image.open(uploaded_file).convert("RGB")  # Remove alpha channel
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    def post(self, request):
        user = request.user

        serializer = ImageUploadSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({
                "success": False,
                "errors": serializer.errors,
                "message": "Invalid data submitted."
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        youtube_url = data['youtube_video_url']
        time_stamp = data['time_stamp']
        image = data['image']
        question = (data.get('question') or "").strip()
        answer = ""

        # ✅ Extract video info
        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_title = get_video_title_with_cache(video_id)
        if not video_title:
            return Response({
                "success": False,
                "message": "Failed to retrieve video title from YouTube."
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Get or create Video and Session
        video, _ = VideoModel.objects.get_or_create(
            youtube_video_id=video_id,
            user=user,
            defaults={'video_title': video_title, 'video_url': youtube_url}
        )
        session, created = SessionModel.objects.get_or_create(user=user, video=video)
        session_status = "New session created" if created else "Session resumed"

        # ✅ Rate Limiting Logic for Free Users
        if not user.is_premium:
            total_clips = ImageModel.objects.filter(session__user=user).count()
            session_clips = ImageModel.objects.filter(session=session).count()

            if total_clips >= 30:
                return Response({
                    "success": False,
                    "message": "You have reached the total limit of 30 image uploads. Upgrade to premium to continue.",
                    "limit_type": "total",
                    "is_premium": False
                }, status=status.HTTP_403_FORBIDDEN)

            if session_clips >= 5:
                return Response({
                    "success": False,
                    "message": "You can only upload 5 images per YouTube video. Please choose another video or upgrade to premium.",
                    "limit_type": "session",
                    "is_premium": False
                }, status=status.HTTP_403_FORBIDDEN)


        if question:
            try:
                image_bytes = self.convert_png_to_jpeg(image)
                mime_type = 'image/jpeg'

                model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
                response = model.generate_content([
                    question,
                    {"mime_type": mime_type, "data": image_bytes}
                ])
                answer = response.text.strip()
            except Exception as e:
                return Response({
                    "success": False,
                    "message": f"Gemini image model processing failed: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # ✅ Save clip
        clip = ImageModel.objects.create(
            image=image,
            question=question,
            answer=answer,
            time_stamp=time_stamp,
            session=session
        )

        return Response({
            "success": True,
            "message": "Image clip created successfully.",
            "data": {
                'id': clip.id,
                'question': clip.question,
                'answer': clip.answer,
                'session_id': session.id,
                'session_status': session_status,
                'time_stamp': time_stamp,
                'created_at': clip.created_at,
                'image_url': request.build_absolute_uri(clip.image.url)
            }
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        youtube_url = request.query_params.get('youtube_video_url')
        if not youtube_url:
            return Response({
                "success": False,
                "message": "'youtube_video_url' query parameter is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SessionModel.objects.select_related('video').get(
                user=request.user,
                video__youtube_video_id=video_id
            )
        except SessionModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "No active session found for the provided video."
            }, status=status.HTTP_404_NOT_FOUND)

        clips = session.images.all().order_by('time_stamp')

        clips_data = [{
            'id': clip.id,
            'question': clip.question,
            'answer': clip.answer,
            'image_url': request.build_absolute_uri(clip.image.url) if clip.image else None,
            'time_stamp': clip.time_stamp,
            'created_at': clip.created_at
        } for clip in clips]

        video_data = {
            'id': session.video.id,
            'title': session.video.video_title,
            'url': session.video.video_url,
            'youtube_video_id': session.video.youtube_video_id,
            'duration_seconds': session.video.duration_seconds,
            'created_at': session.video.created_at,
            'last_accessed_at': session.video.last_accessed_at
        }

        session_data = {
            'id': session.id,
            'total_watch_time': session.total_watch_time,
            'created_at': session.created_at,
            'last_accessed_at': session.last_accessed_at,
            'is_active': session.is_active
        }

        return Response({
            "success": True,
            "message": "Clips and session details fetched successfully.",
            "video": video_data,
            "session": session_data,
            "clips": clips_data
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        clip_id = request.query_params.get('clip_id')
        if not clip_id:
            return Response({
                "success": False,
                "message": "'clip_id' query parameter is required to delete a clip."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            clip = ImageModel.objects.get(id=clip_id, session__user=request.user)
            clip.delete()
            return Response({
                "success": True,
                "message": "Clip deleted successfully."
            }, status=status.HTTP_204_NO_CONTENT)
        except ImageModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "Clip not found or you do not have permission to delete it."
            }, status=status.HTTP_404_NOT_FOUND)



class CreateNotesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateNoteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Invalid input. Please correct the errors below.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        video_url = serializer.validated_data['youtube_video_url']
        notes = serializer.validated_data['notes']
        time_stamp = serializer.validated_data['time_stamp']

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL. Please enter a valid video link."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_title = get_video_title_with_cache(video_id)
        if not video_title:
            return Response({
                "success": False,
                "message": "Unable to fetch video title from YouTube. Please try again later."
            }, status=status.HTTP_400_BAD_REQUEST)

        video, _ = VideoModel.objects.get_or_create(
            youtube_video_id=video_id,
            defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
        )

        session, created = SessionModel.objects.get_or_create(user=user, video=video)
        session_status = "New session created" if created else "Session resumed"

        note = NotesModel.objects.create(
            session=session,
            notes=notes,
            time_stamp=time_stamp
        )

        return Response({
            "success": True,
            "message": "Note created successfully.",
            "data": {
                'id': note.id,
                'notes': note.notes,
                'session': session.id,
                'session_status': session_status,
                'time_stamp': time_stamp,
                'created_at': note.created_at
            }
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({
                "success": False,
                "message": "'youtube_video_url' query parameter is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SessionModel.objects.get(user=request.user, video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "No active session found for the provided video."
            }, status=status.HTTP_404_NOT_FOUND)

        notes = session.notes.all().order_by('time_stamp')
        notes_data = [{
            'id': note.id,
            'notes': note.notes,
            'time_stamp': note.time_stamp,
            'created_at': note.created_at,
            'updated_at': note.updated_at
        } for note in notes]

        video_data = {
            'id': session.video.id,
            'title': session.video.video_title,
            'url': session.video.video_url,
            'youtube_video_id': session.video.youtube_video_id,
            'duration_seconds': session.video.duration_seconds,
            'created_at': session.video.created_at,
            'last_accessed_at': session.video.last_accessed_at
        }

        session_data = {
            'id': session.id,
            'total_watch_time': session.total_watch_time,
            'created_at': session.created_at,
            'last_accessed_at': session.last_accessed_at,
            'is_active': session.is_active
        }


        return Response({
            "success": True,
            "message": "Notes and session details fetched successfully.",
            "video": video_data,
            "session": session_data,
            "notes": notes_data
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        note_id = request.query_params.get('note_id')
        if not note_id:
            return Response({
                "success": False,
                "message": "'note_id' query parameter is required to delete a note."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            note = NotesModel.objects.get(id=note_id, session__user=request.user)
            note.delete()
            return Response({
                "success": True,
                "message": "Note deleted successfully."
            }, status=status.HTTP_204_NO_CONTENT)
        except NotesModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "Note not found or you do not have permission to delete it."
            }, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        note_id = request.data.get('note_id')
        if not note_id:
            return Response({
                "success": False,
                "message": "'note_id' field is required to update a note."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            note = NotesModel.objects.get(id=note_id, session__user=request.user)
        except NotesModel.DoesNotExist:
            return Response({
                "success": False,
                "message": "Note not found or you do not have permission to edit it."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CreateNoteSerializer(note, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Invalid input. Please correct the errors below.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        return Response({
            "success": True,
            "message": "Note updated successfully.",
            "data": {
                "id": note.id,
                "notes": note.notes,
                "time_stamp": note.time_stamp,
                "updated_at": note.updated_at
            }
        }, status=status.HTTP_200_OK)


class CombinedDataAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({
                'status': 'error',
                'message': 'youtube_video_url is required.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                'status': 'error',
                'message': 'Invalid YouTube URL.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SessionModel.objects.get(user=request.user, video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Session not found for this video.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        qas = session.qas.all().order_by('time_stamp')
        notes = session.notes.all().order_by('time_stamp')
        images = session.images.all().order_by('time_stamp')

        data = {
            'session_id': session.id,
            'video_title': session.video.video_title,
            'video_url': session.video.video_url,
            'qa': [
                {
                    'id': qa.id,
                    'question': qa.question,
                    'answer': qa.answer,
                    'time_stamp': qa.time_stamp,
                    'created_at': qa.created_at,
                    'updated_at': qa.updated_at
                } for qa in qas
            ],
            'notes': [
                {
                    'id': note.id,
                    'notes': note.notes,
                    'time_stamp': note.time_stamp,
                    'created_at': note.created_at,
                    'updated_at': note.updated_at
                } for note in notes
            ],
            'images': [
                {
                    'id': image.id,
                    'image_url': request.build_absolute_uri(image.image.url),
                    'question': image.question,
                    'answer': image.answer,
                    'time_stamp': image.time_stamp,
                    'created_at': image.created_at
                } for image in images
            ]
        }

        return Response({
            'status': 'success',
            'message': 'Session data retrieved successfully.',
            'data': data
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({
                'status': 'error',
                'message': 'youtube_video_url is required.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                'status': 'error',
                'message': 'Invalid YouTube URL.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = SessionModel.objects.get(user=request.user, video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Session not found for this video.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        session_id = session.id
        session.delete()

        return Response({
            'status': 'success',
            'message': f'Session with ID {session_id} and all its data (QAs, Notes, Images) have been deleted.',
            'data': None
        }, status=status.HTTP_200_OK)




class CourseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            courses = CourseModel.objects.filter(user=request.user)
            serializer = CourseModelSerializer(courses, many=True)

            return Response({
                'status': 'success',
                'message': f'{len(courses)} course(s) retrieved successfully.',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to retrieve courses.',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = CourseModelSerializer(data=data)

        if serializer.is_valid():
            course = serializer.save()
            return Response({
                'message': 'Course created successfully.',
                'course': CourseModelSerializer(course).data
            }, status=status.HTTP_201_CREATED)

        return Response({
            'message': 'Failed to create course.',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            course = get_object_or_404(CourseModel, pk=pk, user=request.user)
            course_name = course.course_name
            course.delete()
            return Response({
                'status': 'success',
                'message': f'Course "{course_name}" deleted successfully.'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to delete course.',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


# class VideoAPIView(APIView):
#     permission_classes = [IsAuthenticated]
#
#     def post(self, request):
#         video_url = request.data.get('youtube_video_url')
#         if not video_url:
#             return Response(
#                 {"status": "error", "message": "youtube_video_url is required."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         video_id = extract_youtube_video_id(video_url)
#         if not video_id:
#             return Response(
#                 {"status": "error", "message": "Invalid YouTube URL. Please provide a valid link."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         video_title = request.data.get('video_title')
#         if not video_title:
#             video_title = get_video_title_with_cache(video_id)
#             if not video_title:
#                 return Response(
#                     {"status": "error", "message": "Unable to fetch video title. Please try again later."},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
#
#         try:
#             video, video_created = VideoModel.objects.update_or_create(
#                 youtube_video_id=video_id,
#                 defaults={
#                     'video_title': video_title,
#                     'video_url': video_url,
#                     'user': request.user
#                 }
#             )
#
#             session, session_created = SessionModel.objects.get_or_create(
#                 user=request.user,
#                 video=video,
#                 defaults={
#                     'is_active': True,
#                     'total_watch_time': 0
#                 }
#             )
#
#             if not session_created:
#                 session.is_active = True
#                 session.save(update_fields=['is_active', 'last_accessed_at'])
#
#             return Response({
#                 "status": "success",
#                 "message": "Video saved successfully." if video_created else "Video updated successfully.",
#                 "video": VideoSerializer(video).data,
#                 "session": {
#                     "id": session.id,
#                     "is_active": session.is_active,
#                     "total_watch_time": session.total_watch_time,
#                     "last_accessed_at": session.last_accessed_at,
#                     "created_at": session.created_at
#                 },
#                 "status_flags": {
#                     "video_created": video_created,
#                     "session_created": session_created,
#                     "session_reactivated": not session_created and session.is_active
#                 }
#             }, status=status.HTTP_201_CREATED if video_created else status.HTTP_200_OK)
#
#         except Exception as e:
#             return Response({
#                 "status": "error",
#                 "message": "Failed to save video.",
#                 "error": str(e)
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class VideoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        video_url = request.data.get('youtube_video_url')
        if not video_url:
            return Response(
                {"status": "error", "message": "youtube_video_url is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response(
                {"status": "error", "message": "Invalid YouTube URL. Please provide a valid link."},
                status=status.HTTP_400_BAD_REQUEST
            )

        video_title = request.data.get('video_title') or get_video_title_with_cache(video_id)
        if not video_title:
            return Response(
                {"status": "error", "message": "Unable to fetch video title. Please try again later."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Create or update video
            video, video_created = VideoModel.objects.update_or_create(
                youtube_video_id=video_id,
                defaults={
                    'video_title': video_title,
                    'video_url': video_url,
                    'user': request.user
                }
            )

            # Create or reactivate session
            session, session_created = SessionModel.objects.get_or_create(
                user=request.user,
                video=video,
                defaults={
                    'is_active': True,
                    'total_watch_time': 0
                }
            )

            if not session_created:
                session.is_active = True
                session.save(update_fields=['is_active', 'last_accessed_at'])

            # 🔍 Fetch transcript object if it exists
            # 🔍 Fetch transcript object if it exists
            transcript_obj = TranscriptModel.objects.filter(youtube_video_id=video_id).first()
            transcript_created = False  # ✅ Initialize to avoid UnboundLocalError

            # ✅ Print existing transcript (if found)
            if transcript_obj:
                print("✅ Existing transcript found:")
                print("Transcript Text Preview:", transcript_obj.transcript_text)  # preview first 200 chars
            else:
                print("❌ No transcript found. Fetching from API...")

                # 🧠 Get transcript from external source
                transcript_data = get_transcript_with_cache(video_id)
                print("Transcript API Response:", transcript_data)

                if transcript_data:
                    transcript_obj, transcript_created = TranscriptModel.objects.get_or_create(
                        youtube_video_id=video_id,
                        defaults={
                            'language': 'en',
                            'transcript_data': transcript_data.get("segments", []),
                            'transcript_text': transcript_data.get("full_text", "")
                        }
                    )
                    print("✅ Transcript created in DB:", transcript_created)
                    print("Transcript Text:", transcript_data.get("full_text", ""))  # preview
                else:
                    print("❌ No transcript available from API.")

            return Response({
                "status": "success",
                "message": "Video saved successfully." if video_created else "Video updated successfully.",
                "video": VideoSerializer(video).data,
                "session": {
                    "id": session.id,
                    "is_active": session.is_active,
                    "total_watch_time": session.total_watch_time,
                    "last_accessed_at": session.last_accessed_at,
                    "created_at": session.created_at
                },
                "status_flags": {
                    "video_created": video_created,
                    "session_created": session_created,
                    "session_reactivated": not session_created and session.is_active,
                    "transcript_created": transcript_created
                }
            }, status=status.HTTP_201_CREATED if video_created else status.HTTP_200_OK)


        except Exception as e:
            return Response({
                "status": "error",
                "message": "Failed to save video.",
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        try:
            queryset = VideoModel.objects.filter(user=request.user)

            # Optional filter by course
            if course_id := request.query_params.get('course_id'):
                queryset = queryset.filter(course_id=course_id)

            serializer = VideoSerializer(queryset.order_by('-last_accessed_at'), many=True)
            return Response({
                "status": "success",
                "message": "Videos retrieved successfully.",
                "videos": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": "Failed to retrieve videos.",
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        if video_id := request.query_params.get('id'):
            try:
                video = VideoModel.objects.get(id=video_id, user=request.user)
                video_title = video.video_title
                video.delete()
                return Response(
                    {"message": f"Video '{video_title}' deleted successfully."},
                    status=status.HTTP_200_OK
                )
            except VideoModel.DoesNotExist:
                return Response(
                    {"error": "Video not found or you do not have permission to delete it."},
                    status=status.HTTP_404_NOT_FOUND
                )

        elif video_ids := request.query_params.get('ids'):
            ids = [int(id) for id in video_ids.split(',') if id.isdigit()]
            if not ids:
                return Response(
                    {"error": "No valid video IDs provided for deletion."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            deleted_count, _ = VideoModel.objects.filter(
                id__in=ids,
                user=request.user
            ).delete()

            if deleted_count == 0:
                return Response(
                    {"error": "No matching videos found to delete."},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(
                {"message": f"{deleted_count} video(s) deleted successfully."},
                status=status.HTTP_200_OK
            )

        return Response(
            {"error": "Please provide either a single 'id' or multiple 'ids' as a comma-separated list."},
            status=status.HTTP_400_BAD_REQUEST
        )

class VideoCourseUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            video = get_object_or_404(VideoModel, pk=pk, user=request.user)
            serializer = VideoSerializer(video)
            return Response({
                "message": "Video retrieved successfully.",
                "video": serializer.data
            }, status=status.HTTP_200_OK)
        else:
            videos = VideoModel.objects.filter(user=request.user)
            serializer = VideoSerializer(videos, many=True)
            return Response({
                "message": "All videos retrieved successfully.",
                "videos": serializer.data
            }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        video = get_object_or_404(VideoModel, pk=pk, user=request.user)

        serializer = VideoCourseUpdateSerializer(
            video,
            data=request.data,
            partial=True,
            context={'request': request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Video updated successfully.",
                "updated_video": serializer.data
            }, status=status.HTTP_200_OK)

        return Response({
            "error": "Invalid data. Please correct the errors and try again.",
            "details": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)



class YoutubeVideoCourseUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        youtube_url = request.data.get('video_url')
        if not youtube_url:
            return Response({
                "success": False,
                "message": "You must provide a valid 'video_url' field."
            }, status=status.HTTP_400_BAD_REQUEST)

        youtube_video_id = extract_youtube_video_id(youtube_url)
        if not youtube_video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL. Please provide a valid YouTube video link."
            }, status=status.HTTP_400_BAD_REQUEST)

        video = get_object_or_404(VideoModel, youtube_video_id=youtube_video_id, user=request.user)

        serializer = VideoCourseUpdateSerializer(
            video,
            data=request.data,
            partial=True,
            context={'request': request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Video details updated successfully.",
                "updated_video": serializer.data
            }, status=status.HTTP_200_OK)

        return Response({
            "success": False,
            "message": "Update failed. Please correct the highlighted fields.",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class CourseVideoListView(ListAPIView):
    serializer_class = VideoSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Remove pagination

    def get_queryset(self):
        self.search_term = self.request.query_params.get('course_name', '').strip().lower()
        self.user = self.request.user

        if not self.search_term:
            return VideoModel.objects.none()

        base_queryset = VideoModel.objects.filter(user=self.user, course__isnull=False)

        self.exact_match_exists = base_queryset.filter(
            course__course_name__iexact=self.search_term
        ).exists()

        if self.exact_match_exists:
            return base_queryset.filter(
                course__course_name__iexact=self.search_term
            ).order_by('-last_accessed_at')
        else:
            return base_queryset.filter(
                course__course_name__icontains=self.search_term
            ).order_by('-last_accessed_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        if not self.search_term:
            return Response(
                {"success": False, "message": "Please provide a valid 'course_name' query parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not queryset.exists():
            return Response(
                {"success": False, "message": f"No videos found for course name: '{self.search_term}'"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(queryset, many=True)
        match_message = (
            f"Exact match found for course name: '{self.search_term}'"
            if self.exact_match_exists else
            f"No exact match. Showing partial matches for: '{self.search_term}'"
        )

        return Response({
            "success": True,
            "message": match_message,
            "count": len(serializer.data),
            "videos": serializer.data
        }, status=status.HTTP_200_OK)


class UnlinkedVideosAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unlinked_videos = VideoModel.objects.filter(
            user=request.user,
            course__isnull=True
        ).order_by('-last_accessed_at')

        if not unlinked_videos.exists():
            return Response({
                "success": False,
                "message": "No unlinked videos found for the current user.",
                "data": []
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = VideoSerializer(unlinked_videos, many=True)
        return Response({
            "success": True,
            "message": f"{len(serializer.data)} unlinked video(s) retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)



class CourseVideosAPIView(APIView):
    def get(self, request, course_id):
        course = get_object_or_404(CourseModel, id=course_id)
        videos = VideoModel.objects.filter(course=course).order_by('-last_accessed_at')

        if not videos.exists():
            return Response({
                "success": False,
                "message": f"No videos found for course: '{course.course_name}'.",
                "data": []
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = VideoSerializer(videos, many=True)
        return Response({
            "success": True,
            "message": f"{len(serializer.data)} video(s) found for course: '{course.course_name}'.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AllUsersWatchedSessionsView(APIView):
    def get(self, request):
        sessions = SessionModel.objects.select_related('video').prefetch_related('qas')

        # Only select necessary fields for public data
        serializer = allusersSessionSerializer(sessions, many=True, context={'exclude_user': True})
        return Response(serializer.data)



class UserClipWatchedSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        sessions = SessionModel.objects.filter(user=user).select_related('video').prefetch_related('images')
        serializer = SessionModelSerializer(sessions, many=True)
        return Response(serializer.data)

class GetNotesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        sessions = SessionModel.objects.filter(user=user).select_related('video').prefetch_related('notes')
        serializer = NotesSessionModelSerializer(sessions, many=True)
        return Response(serializer.data)
class UserQaWatchedSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        sessions = SessionModel.objects.filter(user=user).select_related('video').prefetch_related('qas')
        serializer = SessionSerializer(sessions, many=True)
        return Response(serializer.data)

class CreateSessionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateSessionSerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                "success": False,
                "error_type": "validation_error",
                "message": "Invalid input. Please correct the errors below.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        video_url = serializer.validated_data['youtube_video_url']

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                "success": False,
                "error_type": "invalid_url",
                "message": "Invalid YouTube URL. Please enter a valid video link."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_title = get_video_title_with_cache(video_id)
        if not video_title:
            return Response({
                "success": False,
                "error_type": "fetch_error",
                "message": "Unable to fetch video title from YouTube. Please try again later."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            video, _ = VideoModel.objects.get_or_create(
                youtube_video_id=video_id,
                defaults={
                    'video_title': video_title,
                    'video_url': video_url,
                    'user': user
                }
            )

            # Get or create the session
            session, created = SessionModel.objects.get_or_create(user=user, video=video)
            session_status = "New session created" if created else "Session resumed"

            return Response({
                "success": True,
                "message": session_status,
                "session": {
                    "session_id": session.id,
                    "video_title": video_title,
                    "video_url": video_url,
                    "created_at": session.created_at.isoformat()
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "success": False,
                "error_type": "server_error",
                "message": "An unexpected error occurred while creating the session.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class YoutubeTranscriptView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = YoutubeTranscriptSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            video_url = serializer.validated_data['youtube_video_url']

            video_id = extract_youtube_video_id(video_url)
            if not video_id:
                return Response({
                    "success": False,
                    "message": "Invalid YouTube URL."
                }, status=status.HTTP_400_BAD_REQUEST)

            video_title = get_video_title_with_cache(video_id)
            if not video_title:
                return Response({
                    "success": False,
                    "message": "Could not retrieve video title."
                }, status=status.HTTP_400_BAD_REQUEST)

            video, _ = VideoModel.objects.get_or_create(
                youtube_video_id=video_id,
                defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
            )

            session, created = SessionModel.objects.get_or_create(user=user, video=video)
            session_status = "New session created" if created else "Session resumed"

            # 🟨 Try fetching from DB cache (TranscriptModel)
            transcript_obj = TranscriptModel.objects.filter(youtube_video_id=video_id).first()
            full_transcript = transcript_obj.transcript_data if transcript_obj else None
            transcript_source = "database"

            if not full_transcript:
                # 🟧 Fallback to yt-dlp or YouTube fetch logic
                transcript_data = get_transcript_with_cache(video_id)
                full_transcript = transcript_data.get("segments") if transcript_data else None
                transcript_source = "fetched"

                if full_transcript:
                    TranscriptModel.objects.create(
                        youtube_video_id=video_id,
                        language='en',
                        transcript_data=full_transcript,
                        transcript_text=transcript_data.get("full_text", "")
                    )

            if not full_transcript:
                return Response({
                    "success": False,
                    "message": "Transcript not available in English. Try with a video that has English subtitles."
                }, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Segmenting the transcript
            segment_duration = 300  # 5 minutes
            segmented_transcripts = {}

            for entry in full_transcript:
                segment_start = int(entry['start'] // segment_duration) * segment_duration
                if segment_start not in segmented_transcripts:
                    segmented_transcripts[segment_start] = []
                segmented_transcripts[segment_start].append(entry['text'])

            formatted_segments = {
                f"{start // 60}m - {(start + segment_duration) // 60}m":
                    " ".join(texts)
                for start, texts in segmented_transcripts.items()
            }

            return Response({
                "success": True,
                "message": f"Transcript split successfully from {transcript_source}.",
                "video_title": video_title,
                "video_url": video_url,
                "session_id": session.id,
                "session_status": session_status,
                "transcript_segments": formatted_segments,
                "transcript_source": transcript_source  # 🆕 Show where it came from
            }, status=status.HTTP_200_OK)

        return Response({
            "success": False,
            "message": "Invalid input data.",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

# class YoutubeTranscriptView(APIView):
#     permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        video_url = request.query_params.get('youtube_video_url')

        if not video_url:
            return Response({
                "success": False,
                "message": "Missing 'youtube_video_url' query parameter."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({
                "success": False,
                "message": "Invalid YouTube URL."
            }, status=status.HTTP_400_BAD_REQUEST)

        video_title = get_video_title_with_cache(video_id)
        if not video_title:
            return Response({
                "success": False,
                "message": "Could not retrieve video title."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 🔁 Get or create video
        video, _ = VideoModel.objects.get_or_create(
            youtube_video_id=video_id,
            defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
        )

        # 🔁 Get or create session
        session, created = SessionModel.objects.get_or_create(user=user, video=video)
        session_status = "New session created" if created else "Session resumed"

        # 🔁 Check DB first
        transcript_obj = TranscriptModel.objects.filter(youtube_video_id=video_id).first()
        full_transcript = transcript_obj.transcript_data if transcript_obj else None
        transcript_source = "database"

        if not full_transcript:
            # ⏬ Try fetching from YouTube
            transcript_data = get_transcript_with_cache(video_id)
            full_transcript = transcript_data.get("segments") if transcript_data else None
            transcript_source = "fetched"

            if full_transcript:
                TranscriptModel.objects.create(
                    youtube_video_id=video_id,
                    language='en',
                    transcript_data=full_transcript,
                    transcript_text=transcript_data.get("full_text", "")
                )

        if not full_transcript:
            return Response({
                "success": False,
                "message": "Transcript not available in English. Try with a video that has English subtitles."
            }, status=status.HTTP_400_BAD_REQUEST)


        segment_duration = 60
        segmented_transcripts = {}

        for entry in full_transcript:
            segment_start = int(entry['start'] // segment_duration) * segment_duration
            if segment_start not in segmented_transcripts:
                segmented_transcripts[segment_start] = []
            segmented_transcripts[segment_start].append(entry['text'])

        formatted_segments = {
            f"{start // 60}m - {(start + segment_duration) // 60}m":
                " ".join(texts)
            for start, texts in segmented_transcripts.items()
        }

        return Response({
            "success": True,
            "message": f"Transcript split successfully from {transcript_source}.",
            "video_title": video_title,
            "video_url": video_url,
            # "session_id": session.id,
            # "session_status": session_status,
            "transcript_segments": formatted_segments,
            "transcript_source": transcript_source
        }, status=status.HTTP_200_OK)
from rest_framework.generics import ListAPIView
from .models import TranscriptModel
from .serializers import TranscriptSerializer
from rest_framework.pagination import PageNumberPagination
class TranscriptPagination(PageNumberPagination):
    page_size = 10  # Or 20, 50, etc. depending on performance
class TranscriptListAPIView(ListAPIView):
    queryset = TranscriptModel.objects.all().order_by('-created_at')
    serializer_class = TranscriptSerializer
    pagination_class = TranscriptPagination



# views.py

from .models import  MCQModel

from django.utils import timezone
# from .mcq_utils import *  # move your long logic to `mcq_utils.py`

# User = get_user_model()

# class GenerateMCQsAPIView(APIView):
#     def post(self, request):
#         youtube_url = request.data.get('youtube_url')
#         user = request.user
#
#         if not youtube_url:
#             return Response({'error': 'youtube_url is required'}, status=400)
#
#         video_id = extract_youtube_video_id(youtube_url)
#         if not video_id:
#             return Response({
#                 "success": False,
#                 "message": "Invalid YouTube URL."
#             }, status=status.HTTP_400_BAD_REQUEST)
#
#         video_title = get_video_title_with_cache(video_id, settings.YOUTUBE_API_KEY)
#         if not video_title:
#             return Response({
#                 "success": False,
#                 "message": "Could not retrieve video title."
#             }, status=status.HTTP_400_BAD_REQUEST)
#
#         video, _ = VideoModel.objects.get_or_create(
#             user=user,
#             youtube_video_id=video_id,
#             defaults={'video_title': video_title, 'video_url': youtube_url}
#         )
#
#         session, created = SessionModel.objects.get_or_create(user=user, video=video)
#
#         # Get transcript
#         transcript = get_transcript_from_youtube(video_id)
#         if not transcript:
#             return Response({'error': 'Transcript fetch failed'}, status=500)
#
#         # Generate MCQs
#         full_transcript = " ".join([line["text"] for line in transcript])
#         mcq_text = generate_mcqs_from_transcript(full_transcript)
#         if not mcq_text:
#             return Response({'error': 'MCQ generation failed'}, status=500)
#
#         mcqs = parse_mcqs_to_json(mcq_text)
#         if not mcqs:
#             return Response({'error': 'MCQ parsing failed'}, status=500)
#
#         # Save to DB
#         for mcq in mcqs:
#             MCQModel.objects.create(
#                 session=session,
#                 question_text=mcq["question"],
#                 option_a=mcq["options"]["A"],
#                 option_b=mcq["options"]["B"],
#                 option_c=mcq["options"]["C"],
#                 option_d=mcq["options"]["D"],
#                 correct_option=mcq["correct_answer"],
#                 explanation=mcq["explanation"],
#                 difficulty=mcq["difficulty"],
#                 question_type=mcq["question_type"]
#             )
#
#         return Response({
#             "message": "MCQs generated and saved successfully",
#             "video_id": video.youtube_video_id,
#             "total_questions": len(mcqs),
#         }, status=201)
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import logging

from .models import VideoModel, SessionModel, TranscriptModel, MCQModel,MCQSubmission
from .serializers import MCQModelSerializer
from .utils import (
    extract_youtube_video_id,
    get_video_title_with_cache,
    get_transcript_with_cache,
    classify_question_type,
    generate_mcqs_from_transcript,  # your new logic
)

logger = logging.getLogger(__name__)

ALLOWED_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced", "Expert"}


class GenerateMCQsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        youtube_url = request.data.get("youtube_url")

        if not youtube_url:
            return Response({"detail": "youtube_url is required."}, status=status.HTTP_400_BAD_REQUEST)

        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return Response({"success": False, "message": "Invalid YouTube URL."}, status=status.HTTP_400_BAD_REQUEST)

        video_title = get_video_title_with_cache(video_id, settings.YOUTUBE_API_KEY)
        if not video_title:
            return Response({"success": False, "message": "Could not retrieve video title."}, status=status.HTTP_400_BAD_REQUEST)

        video, _ = VideoModel.objects.get_or_create(
            user=user,
            youtube_video_id=video_id,
            defaults={'video_title': video_title, 'video_url': youtube_url}
        )
        session, _ = SessionModel.objects.get_or_create(user=user, video=video)

        transcript_obj = TranscriptModel.objects.filter(youtube_video_id=video_id).first()
        full_transcript = transcript_obj.transcript_text if transcript_obj else None

        if not full_transcript:
            try:
                transcript_data = get_transcript_with_cache(video_id)
                full_transcript = transcript_data.get("full_text")
                segments = transcript_data.get("segments")

                if full_transcript and segments:
                    TranscriptModel.objects.create(
                        youtube_video_id=video_id,
                        language='en',
                        transcript_data=segments,
                        transcript_text=full_transcript
                    )
            except Exception:
                logger.exception("Transcript fetch failed.")
                return Response({"error": "Transcript fetch failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not full_transcript:
            return Response({
                "success": False,
                "message": "No transcript data found for this video."
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            mcqs = generate_mcqs_from_transcript(full_transcript)
            if not mcqs:
                return Response({"detail": "Parsing Gemini response failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception:
            logger.exception("MCQ generation failed")
            return Response({"detail": "Failed to generate MCQs."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        saved_mcqs = []
        for mcq in mcqs:
            question = mcq.get("question")
            options = mcq.get("options", {})
            correct_answer = mcq.get("correct_answer")
            explanation = mcq.get("explanation", "")
            difficulty = mcq.get("difficulty", "").capitalize()

            if difficulty not in ALLOWED_DIFFICULTIES:
                difficulty = "Intermediate"

            # ✅ Validate MCQ format before saving
            if question and len(options) == 4 and all(k in options for k in ["A", "B", "C", "D"]) and correct_answer:
                question_type = classify_question_type(question)
                saved = MCQModel.objects.create(
                    session=session,
                    question_text=question,
                    option_a=options.get("A", ""),
                    option_b=options.get("B", ""),
                    option_c=options.get("C", ""),
                    option_d=options.get("D", ""),
                    correct_option=correct_answer,
                    explanation=explanation,
                    difficulty=difficulty,
                    question_type=question_type,
                )
                saved_mcqs.append(saved)
        serializer = MCQModelSerializer(saved_mcqs, many=True)
        return Response({
            "video_id": video_id,
            "success": True,
            "message": f"{len(saved_mcqs)} MCQs generated successfully.",
            "mcqs": serializer.data
        }, status=status.HTTP_201_CREATED)


# from django.shortcuts import get_object_or_404
#
# class SubmitMCQAnswersAPIView(APIView):
#     permission_classes = [IsAuthenticated]
#
#     def post(self, request):
#         user = request.user
#         youtube_video_id = request.data.get("video_id")
#         answers = request.data.get("answers", [])
#
#         if not youtube_video_id:
#             return Response({"detail": "video_id is required."}, status=status.HTTP_400_BAD_REQUEST)
#
#         if not isinstance(answers, list) or not answers:
#             return Response({"detail": "Invalid or missing answers."}, status=status.HTTP_400_BAD_REQUEST)
#
#         # Use unique constraint to safely get the video
#         try:
#             video = VideoModel.objects.get(user=user, youtube_video_id=youtube_video_id)
#         except VideoModel.DoesNotExist:
#             return Response({"detail": "Video not found. Generate MCQs first."}, status=status.HTTP_404_NOT_FOUND)
#         except VideoModel.MultipleObjectsReturned:
#             return Response({"detail": "Multiple videos found. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#
#         # Get or create the session
#         session, _ = SessionModel.objects.get_or_create(user=user, video=video)
#
#         results = []
#         for answer in answers:
#             mcq_id = answer.get("mcq_id")
#             selected = answer.get("selected_option", "").upper()
#
#             if not mcq_id or selected not in ['A', 'B', 'C', 'D']:
#                 continue
#
#             try:
#                 mcq = MCQModel.objects.get(id=mcq_id, session=session)
#             except MCQModel.DoesNotExist:
#                 continue
#
#             is_correct = selected == mcq.correct_option.upper()
#
#             # Create or update the submission
#             try:
#                 submission, _ = MCQSubmission.objects.update_or_create(
#                     user=user,
#                     session=session,
#                     mcq=mcq,
#                     defaults={
#                         "selected_option": selected,
#                         "is_correct": is_correct,
#                     }
#                 )
#                 results.append({
#                     "mcq_id": mcq.id,
#                     "question":mcq.question_text,
#                     "selected_option": selected,
#                     "is_correct": is_correct,
#                     "correct_option": mcq.correct_option.upper(),
#                     "explanation": mcq.explanation or "",
#                 })
#             except Exception as e:
#                 # Optional: log error here
#                 continue
#
#         return Response({
#             "success": True,
#             "message": "Answers submitted successfully.",
#             "results": results
#         }, status=status.HTTP_200_OK)

from django.shortcuts import get_object_or_404

class SubmitMCQAnswersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        youtube_video_id = request.data.get("video_id")
        answers = request.data.get("answers", [])

        if not youtube_video_id:
            return Response({"detail": "video_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(answers, list) or not answers:
            return Response({"detail": "Invalid or missing answers."}, status=status.HTTP_400_BAD_REQUEST)

        # Get the video safely
        try:
            video = VideoModel.objects.get(user=user, youtube_video_id=youtube_video_id)
        except VideoModel.DoesNotExist:
            return Response({"detail": "Video not found. Generate MCQs first."}, status=status.HTTP_404_NOT_FOUND)
        except VideoModel.MultipleObjectsReturned:
            return Response({"detail": "Multiple videos found. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Get or create the session
        session, _ = SessionModel.objects.get_or_create(user=user, video=video)

        results = []
        for answer in answers:
            mcq_id = answer.get("mcq_id")
            selected = answer.get("selected_option", "").upper()

            if not mcq_id or selected not in ['A', 'B', 'C', 'D']:
                continue

            try:
                mcq = MCQModel.objects.get(id=mcq_id, session=session)
            except MCQModel.DoesNotExist:
                continue

            is_correct = selected == mcq.correct_option.upper()

            # Get correct option content dynamically
            correct_label = mcq.correct_option.upper()
            correct_content = getattr(mcq, f"option_{correct_label.lower()}", "")
            correct_option_full = f"{correct_label}: {correct_content}"

            # Create or update submission
            try:
                submission, _ = MCQSubmission.objects.update_or_create(
                    user=user,
                    session=session,
                    mcq=mcq,
                    defaults={
                        "selected_option": selected,
                        "is_correct": is_correct,
                    }
                )

                results.append({
                    "mcq_id": mcq.id,
                    "question": mcq.question_text,
                    "selected_option": selected,
                    "is_correct": is_correct,
                    "correct_option": correct_option_full,
                    "explanation": mcq.explanation or "",
                })
            except Exception:
                continue

        return Response({
            "success": True,
            "message": "Answers submitted successfully.",
            "results": results
        }, status=status.HTTP_200_OK)
