
import io
import mimetypes
from urllib.parse import urlparse, parse_qs
from rest_framework.generics import UpdateAPIView
import google.generativeai as genai
from django.conf import settings
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from PIL import Image
from rest_framework import status, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from django.db.models import Q
from .models import ImageModel, NotesModel, QAModel, SessionModel, VideoModel, CourseModel
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
    CreateSessionSerializer
)




genai.configure(api_key=settings.GEMINI_API_KEY)
YOUTUBE_API_KEY = settings.YOUTUBE_API_KEY


def extract_youtube_video_id(url):
    parsed_url = urlparse(url)
    if 'youtu.be' in parsed_url.hostname:
        return parsed_url.path[1:]
    elif 'youtube.com' in parsed_url.hostname:
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        elif parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/embed/')[1]
    return None


def fetch_video_title(video_id):
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    try:
        response = youtube.videos().list(part="snippet", id=video_id).execute()
        if response['items']:
            return response['items'][0]['snippet']['title']
    except HttpError as e:
        raise Exception(f"Failed to fetch video title: {str(e)}")
    return None


# Fetch transcript from YouTubeTranscriptApi
def fetch_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        try:
            transcript = transcript_list.find_transcript(['en'])
            return transcript.fetch()
        except:
            pass

        for transcript in transcript_list:
            try:
                return transcript.fetch()
            except:
                continue

    except NoTranscriptFound:
        return None
    except Exception as e:
        print(f"Error fetching transcript: {str(e)}")
        return None


class AskQuestionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = YoutubeSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            video_url = serializer.validated_data['youtube_video_url']
            question = serializer.validated_data['question']
            time_stamp = serializer.validated_data['time_stamp']

            video_id = extract_youtube_video_id(video_url)
            if not video_id:
                return Response({'error': 'Invalid YouTube URL.'}, status=400)

            video_title = fetch_video_title(video_id)
            if not video_title:
                return Response({'error': 'Could not retrieve video title.'}, status=400)

            video, _ = VideoModel.objects.get_or_create(
                youtube_video_id=video_id,
                defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
            )

            session, created = SessionModel.objects.get_or_create(user=user, video=video)
            session_status = "New session created" if created else "Session resumed"

            full_transcript = fetch_transcript(video_id)
            if not full_transcript:
                return Response({
                    'error': 'Transcript not available in English. Try with a video that has English subtitles.'
                }, status=400)

            # Filter transcript around ±60 seconds of timestamp
            start_range = max(0, time_stamp - 60)
            end_range = time_stamp + 60

            transcript_segment = " ".join([
                entry.text for entry in full_transcript
                if start_range <= entry.start <= end_range
            ])

            if not transcript_segment.strip():
                return Response({'error': 'No transcript data found near the timestamp.'}, status=400)

            prompt = (
                f"You are a helpful assistant. Based only on the following segment of a YouTube video transcript, "
                f"which is from around timestamp {time_stamp} seconds, answer the user's question.\n\n"
                f"Transcript Segment:\n{transcript_segment}\n\n"
                f"Question: {question}\nAnswer:"
            )

            try:
                model = genai.GenerativeModel('gemini-1.5-pro')
                response = model.generate_content(prompt)
                answer = response.text.strip()
            except Exception as e:
                return Response({'error': f'Gemini API failed: {str(e)}'}, status=500)

            qa = QAModel.objects.create(
                session=session,
                question=question,
                answer=answer,
                time_stamp=time_stamp
            )

            return Response({
                'id': qa.id,
                'question': qa.question,
                'answer': qa.answer,
                'transcript_segment': transcript_segment,
                'session': session.id,
                'session_status': session_status,
                'time_stamp': qa.time_stamp,
                'created_at': qa.created_at
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({'error': 'youtube_video_url is required.'}, status=400)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL.'}, status=400)

        try:
            session = SessionModel.objects.select_related('video').get(user=request.user,
                                                                       video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({'error': 'Session not found for this video.'}, status=404)

        qas = session.qas.all().order_by('time_stamp')

        qa_data = [
            {
                'id': qa.id,
                'question': qa.question,
                'answer': qa.answer,
                'time_stamp': qa.time_stamp,
                'created_at': qa.created_at,
                'updated_at': qa.updated_at
            }
            for qa in qas
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
            'video': video_data,
            'session': session_data,
            'qa_list': qa_data
        }, status=200)

    def delete(self, request):
        qa_id = request.query_params.get('id')
        if not qa_id:
            return Response({'error': 'QA id is required to delete.'}, status=400)

        try:
            qa = QAModel.objects.get(id=qa_id, session__user=request.user)
            qa.delete()
            return Response({'message': 'Q&A deleted successfully.'}, status=204)
        except QAModel.DoesNotExist:
            return Response({'error': 'Q&A not found or unauthorized.'}, status=404)



class ClipTabAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def convert_png_to_jpeg(self, uploaded_file):
        """Convert PNG image to JPEG format for Gemini processing."""
        image = Image.open(uploaded_file).convert("RGB")  # Remove alpha channel
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()

    # def post(self, request):
    #     user = request.user
    #     youtube_url = request.data.get('youtube_video_url')
    #     time_stamp = request.data.get('time_stamp')
    #     image = request.FILES.get('image')
    #     question = request.data.get('question', '')
    #
    #     if not youtube_url or not image or time_stamp is None:
    #         return Response({'error': 'youtube_video_url, image, and time_stamp are required.'},
    #                         status=status.HTTP_400_BAD_REQUEST)
    #
    #     # Extract video ID and title
    #     video_id = extract_youtube_video_id(youtube_url)
    #     if not video_id:
    #         return Response({'error': 'Invalid YouTube URL.'}, status=400)
    #
    #     video_title = fetch_video_title(video_id)
    #     if not video_title:
    #         return Response({'error': 'Could not retrieve video title.'}, status=400)
    #
    #     # Get or Create Video
    #     video, _ = VideoModel.objects.get_or_create(
    #         youtube_video_id=video_id,
    #         defaults={'video_title': video_title, 'video_url': youtube_url, 'user': user}
    #     )
    #
    #     # Get or Create Session
    #     session, created = SessionModel.objects.get_or_create(user=user, video=video)
    #     session_status = "New session created" if created else "Session resumed"
    #
    #     # Convert image to JPEG and prepare for Gemini
    #     try:
    #         image_bytes = self.convert_png_to_jpeg(image)
    #         mime_type = 'image/jpeg'
    #
    #         model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
    #         response = model.generate_content([
    #             question,
    #             {
    #                 "mime_type": mime_type,
    #                 "data": image_bytes
    #             }
    #         ])
    #         answer = response.text.strip()
    #     except Exception as e:
    #         return Response({'error': f'Gemini image model failed: {str(e)}'},
    #                         status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    #
    #
    #     clip = ImageModel.objects.create(
    #         image=image,
    #         question=question,
    #         answer=answer,
    #         time_stamp=time_stamp,
    #         session=session
    #     )
    #
    #     return Response({
    #         'id': clip.id,
    #         'question': clip.question,
    #         'answer': clip.answer,
    #         'session_id': session.id,
    #         'session_status': session_status,
    #         'time_stamp': clip.time_stamp,
    #         'created_at': clip.created_at,
    #         'image_url': clip.image.url
    #     }, status=status.HTTP_201_CREATED)

    def post(self, request):
        serializer = ImageUploadSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = request.user
        youtube_url = data['youtube_video_url']
        time_stamp = data['time_stamp']  # Already parsed by TimestampField
        image = data['image']
        question = data.get('question', '')

        # Extract video ID and title
        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL.'}, status=status.HTTP_400_BAD_REQUEST)

        video_title = fetch_video_title(video_id)
        if not video_title:
            return Response({'error': 'Could not retrieve video title.'}, status=status.HTTP_400_BAD_REQUEST)

        # Get or Create Video
        video, _ = VideoModel.objects.get_or_create(
            youtube_video_id=video_id,
            defaults={'video_title': video_title, 'video_url': youtube_url, 'user': user}
        )

        session, created = SessionModel.objects.get_or_create(user=user, video=video)
        session_status = "New session created" if created else "Session resumed"


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
            return Response({'error': f'Gemini image model failed: {str(e)}'},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Save to database
        clip = ImageModel.objects.create(
            image=image,
            question=question,
            answer=answer,
            time_stamp=time_stamp,  # Using parsed timestamp
            session=session
        )

        return Response({
            'id': clip.id,
            'question': clip.question,
            'answer': clip.answer,
            'session_id': session.id,
            'session_status': session_status,
            'time_stamp': time_stamp,  # Return parsed timestamp
            'created_at': clip.created_at,
            'image_url': request.build_absolute_uri(clip.image.url)
        }, status=status.HTTP_201_CREATED)
    def get(self, request):
        youtube_url = request.query_params.get('youtube_video_url')
        if not youtube_url:
            return Response({'error': 'youtube_video_url is required.'}, status=400)

        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL.'}, status=400)

        try:
            session = SessionModel.objects.select_related('video').get(user=request.user,
                                                                       video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({'error': 'Session not found for this video.'}, status=404)

        clips = session.images.all().order_by('time_stamp')

        clips_data = [
            {
                'id': clip.id,
                'question': clip.question,
                'answer': clip.answer,
                'image_url': request.build_absolute_uri(clip.image.url) if clip.image else None,
                'time_stamp': clip.time_stamp,
                'created_at': clip.created_at
            }
            for clip in clips
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
            'video': video_data,
            'session': session_data,
            'clips': clips_data
        }, status=200)

    def delete(self, request):
        clip_id = request.query_params.get('clip_id')
        if not clip_id:
            return Response({'error': 'clip_id is required to delete a clip.'}, status=400)

        try:
            clip = ImageModel.objects.get(id=clip_id, session__user=request.user)
            clip.delete()
            return Response({'message': 'Clip deleted successfully.'}, status=204)
        except ImageModel.DoesNotExist:
            return Response({'error': 'Clip not found or unauthorized.'}, status=404)




class CreateNotesAPIView(APIView):
    permission_classes = [IsAuthenticated]
#
#     def post(self, request):
#         serializer = CreateNoteSerializer(data=request.data)
#         if serializer.is_valid():
#             user = request.user
#             video_url = serializer.validated_data['youtube_video_url']
#             notes = serializer.validated_data['notes']
#             time_stamp = serializer.validated_data['time_stamp']
#
#             video_id = extract_youtube_video_id(video_url)
#             if not video_id:
#                 return Response({'error': 'Invalid YouTube URL.'}, status=400)
#
#             video_title = fetch_video_title(video_id)
#             if not video_title:
#                 return Response({'error': 'Could not retrieve video title.'}, status=400)
#
#             video, _ = VideoModel.objects.get_or_create(
#                 youtube_video_id=video_id,
#                 defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
#             )
#
#             session, created = SessionModel.objects.get_or_create(user=user, video=video)
#             session_status = "New session created" if created else "Session resumed"
#
#             note = NotesModel.objects.create(
#                 session=session,
#                 notes=notes,
#                 time_stamp=time_stamp
#             )
#
#             return Response({
#                 'id': note.id,
#                 'notes': note.notes,
#                 'session': session.id,
#                 'session_status': session_status,
#                 'time_stamp': note.time_stamp,
#                 'created_at': note.created_at
#             }, status=status.HTTP_201_CREATED)
#
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    def post(self, request):
        serializer = CreateNoteSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            video_url = serializer.validated_data['youtube_video_url']
            notes = serializer.validated_data['notes']
            time_stamp = serializer.validated_data['time_stamp']  # Already parsed by TimestampField

            video_id = extract_youtube_video_id(video_url)
            if not video_id:
                return Response({'error': 'Invalid YouTube URL.'}, status=status.HTTP_400_BAD_REQUEST)

            video_title = fetch_video_title(video_id)
            if not video_title:
                return Response({'error': 'Could not retrieve video title.'}, status=status.HTTP_400_BAD_REQUEST)

            video, _ = VideoModel.objects.get_or_create(
                youtube_video_id=video_id,
                defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
            )

            session, created = SessionModel.objects.get_or_create(user=user, video=video)
            session_status = "New session created" if created else "Session resumed"

            note = NotesModel.objects.create(
                session=session,
                notes=notes,
                time_stamp=time_stamp  # Using the parsed timestamp value
            )

            return Response({
                'id': note.id,
                'notes': note.notes,
                'session': session.id,
                'session_status': session_status,
                'time_stamp': time_stamp,  # Return the original parsed value
                'created_at': note.created_at
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    def get(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({'error': 'youtube_video_url is required.'}, status=400)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL.'}, status=400)

        try:
            session = SessionModel.objects.get(user=request.user, video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({'error': 'Session not found for this video.'}, status=404)

        notes = session.notes.all().order_by('time_stamp')
        data = [
            {
                'id': note.id,
                'notes': note.notes,
                'time_stamp': note.time_stamp,
                'created_at': note.created_at,
                'updated_at': note.updated_at
            } for note in notes
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

            'video': video_data,
            'session': session_data,
            'notes': data
        }, status=200)

    def delete(self, request):
        note_id = request.query_params.get('note_id')
        if not note_id:
            return Response({'error': 'note_id is required to delete a note.'}, status=400)

        try:
            note = NotesModel.objects.get(id=note_id, session__user=request.user)
            note.delete()
            return Response({'message': 'Note deleted successfully.'}, status=204)
        except NotesModel.DoesNotExist:
            return Response({'error': 'Note not found or unauthorized.'}, status=404)




class CombinedDataAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({'error': 'youtube_video_url is required.'}, status=400)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL.'}, status=400)

        try:
            session = SessionModel.objects.get(user=request.user, video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({'error': 'Session not found for this video.'}, status=404)

        qas = session.qas.all().order_by('time_stamp')
        notes = session.notes.all().order_by('time_stamp')
        images = session.images.all().order_by('time_stamp')

        return Response({
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
        }, status=200)

    def delete(self, request):
        video_url = request.query_params.get('youtube_video_url')
        if not video_url:
            return Response({'error': 'youtube_video_url is required.'}, status=400)

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL.'}, status=400)

        try:
            # Fetch the session based on video URL and authenticated user
            session = SessionModel.objects.get(user=request.user, video__youtube_video_id=video_id)
        except SessionModel.DoesNotExist:
            return Response({'error': 'Session not found for this video.'}, status=404)

        # Delete the entire session and related data (QA, Notes, Images) will be cascaded
        session_id = session.id  # Capture session id before deletion
        session.delete()

        return Response({
            'message': f'Session with ID {session_id} and all its data (QAs, Notes, Images) have been deleted.'
        }, status=200)




class CourseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        courses = CourseModel.objects.filter(user=request.user)
        serializer = CourseModelSerializer(courses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = CourseModelSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        course = get_object_or_404(CourseModel, pk=pk, user=request.user)
        course.delete()
        return Response({'message': 'Course deleted successfully.'}, status=status.HTTP_200_OK)


class VideoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = VideoModel.objects.filter(user=request.user)

        # Optional course filter
        if course_id := request.query_params.get('course_id'):
            queryset = queryset.filter(course_id=course_id)

        serializer = VideoSerializer(queryset.order_by('-last_accessed_at'), many=True)
        return Response(serializer.data)

    # POST - Create new video
    def post(self, request):
        video_url = request.data.get('youtube_video_url')
        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return Response({'error': 'Invalid YouTube URL'}, status=status.HTTP_400_BAD_REQUEST)

        video_title = request.data.get('video_title')
        if not video_title:
            video_title = fetch_video_title(video_id)
            if not video_title:
                return Response(
                    {'error': 'Could not retrieve video title'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        video, video_created = VideoModel.objects.update_or_create(
            youtube_video_id=video_id,
            defaults={
                'video_title': video_title,
                'video_url': video_url,
                'user': request.user
            }
        )


        session, session_created = SessionModel.objects.get_or_create(
            user=request.user,
            video=video,
            defaults={
                'is_active': True,
                'total_watch_time': 0
            }
        )

        # Update session if it already exists
        if not session_created:
            session.is_active = True
            session.save(update_fields=['is_active', 'last_accessed_at'])

        return Response({
            'video': VideoSerializer(video).data,
            'session': {
                'id': session.id,
                'is_active': session.is_active,
                'total_watch_time': session.total_watch_time,
                'last_accessed_at': session.last_accessed_at,
                'created_at': session.created_at
            },
            'status': {
                'video_created': video_created,
                'session_created': session_created,
                'session_reactivated': not session_created and session.is_active
            }
        }, status=status.HTTP_201_CREATED if video_created else status.HTTP_200_OK)

    # DELETE - Handle both single and bulk deletion
    def delete(self, request):
        # Single deletion case (DELETE /videos/?id=123)
        if video_id := request.query_params.get('id'):
            try:
                video = VideoModel.objects.get(id=video_id, user=request.user)
                video.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except VideoModel.DoesNotExist:
                return Response(
                    {"error": "Video not found or not owned by user"},
                    status=status.HTTP_404_NOT_FOUND
                )

        elif video_ids := request.query_params.get('ids'):
            ids = [int(id) for id in video_ids.split(',') if id.isdigit()]
            if not ids:
                return Response(
                    {"error": "No valid video IDs provided"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            deleted_count, _ = VideoModel.objects.filter(
                id__in=ids,
                user=request.user
            ).delete()

            if deleted_count == 0:
                return Response(
                    {"error": "No videos found matching the criteria"},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(
                {"deleted_count": deleted_count},
                status=status.HTTP_200_OK
            )

        return Response(
            {"error": "Provide either 'id' or 'ids' parameter"},
            status=status.HTTP_400_BAD_REQUEST
        )
class VideoCourseUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:

            video = get_object_or_404(VideoModel, pk=pk, user=request.user)
            serializer = VideoSerializer(video)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:

            videos = VideoModel.objects.filter(user=request.user)
            serializer = VideoSerializer(videos, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):

        video = get_object_or_404(VideoModel, pk=pk, user=request.user)


        serializer = VideoCourseUpdateSerializer(video, data=request.data, partial=True, context={'request': request})

        # Validate and save the serializer
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class CourseVideoListView(ListAPIView):
    serializer_class = VideoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        search_term = self.request.query_params.get('course_name', '').strip().lower()
        user = self.request.user

        if not search_term:
            return VideoModel.objects.none()

        # Base queryset
        queryset = VideoModel.objects.filter(
            user=user,
            course__isnull=False
        )


        exact_match_exists = queryset.filter(
            course__course_name__iexact=search_term
        ).exists()

        if exact_match_exists:

            return queryset.filter(
                course__course_name__iexact=search_term
            ).order_by('-last_accessed_at')
        else:

            return queryset.filter(
                course__course_name__icontains=search_term
            ).order_by('-last_accessed_at')




class UnlinkedVideosAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unlinked_videos = VideoModel.objects.filter(
            user=request.user,
            course__isnull=True
        ).order_by('-last_accessed_at')

        serializer = VideoSerializer(unlinked_videos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
        if serializer.is_valid():
            user = request.user
            video_url = serializer.validated_data['youtube_video_url']


            video_id = extract_youtube_video_id(video_url)
            if not video_id:
                return Response({'error': 'Invalid YouTube URL.'}, status=400)

            # Fetch the video title using the video ID
            video_title = fetch_video_title(video_id)
            if not video_title:
                return Response({'error': 'Could not retrieve video title.'}, status=400)

            # Get or create the video object in the database
            video, _ = VideoModel.objects.get_or_create(
                youtube_video_id=video_id,
                defaults={'video_title': video_title, 'video_url': video_url, 'user': user}
            )

            # Create a session for the user and the video
            session, created = SessionModel.objects.get_or_create(user=user, video=video)
            session_status = "New session created" if created else "Session resumed"

            # Respond with session details and video title
            return Response({
                'session_id': session.id,
                'video_title': video_title,
                'session_status': session_status,
                'created_at': session.created_at
            }, status=status.HTTP_201_CREATED)


        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
