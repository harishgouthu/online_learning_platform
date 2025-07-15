

from django.urls import path
from .views import (CourseAPIView, AskQuestionAPIView, UserQaWatchedSessionsView, VideoAPIView,
                    AllUsersWatchedSessionsView, ClipTabAPIView, UserClipWatchedSessionsView,
                    CreateNotesAPIView,  GetNotesAPIView, CombinedDataAPIView, CreateSessionAPIView,
                    VideoCourseUpdateView, YoutubeVideoCourseUpdateView, UnlinkedVideosAPIView, CourseVideoListView,
                    CourseVideosAPIView, YoutubeTranscriptView, TranscriptListAPIView)

urlpatterns = [
    path('transcripts/', TranscriptListAPIView.as_view(), name='transcript-list'),
    path('courses/', CourseAPIView.as_view(), name='course-api'),
    path('courses/<int:pk>/', CourseAPIView.as_view(), name='course-api-detail'),
    path('unlinked-videos/', UnlinkedVideosAPIView.as_view(), name='unlinked-videos'),
    path('courses/<int:course_id>/videos/', CourseVideosAPIView.as_view(), name='course-videos'),
    path('videos/<int:pk>/update-course/', VideoCourseUpdateView.as_view(), name='video-update-course'),
    path('videos/update-course-by-url/', YoutubeVideoCourseUpdateView.as_view(), name='video-update-course-by-url'),

    path('videos/', VideoAPIView.as_view(), name='video-api'),
    path('search-course/', CourseVideoListView.as_view(), name='course-videos-list'),

    path('ask-question/', AskQuestionAPIView.as_view(), name='ask-question'), #post/get/del

    path('cliptab/', ClipTabAPIView.as_view(), name='cliptab'), #post/get/del

    path('create-note/', CreateNotesAPIView.as_view(), name='create-note'), #post/get/del
    path('notes/<int:note_id>/', CreateNotesAPIView.as_view(), name='update-note'), #edit
    path('youtube/transcript/', YoutubeTranscriptView.as_view(), name='youtube-transcript'),

    path('combined-api/', CombinedDataAPIView.as_view(), name='combinedapi'),#get/del

    path('user-allvideos-qa-watched-sessions/', UserQaWatchedSessionsView.as_view(), name='user-watched-sessions'),#get/
    path('user-allvideos-clip-watched-sessions/', UserClipWatchedSessionsView.as_view(), name='user-watched-sessions'),#get/
    path('user-allvideos-notes-watched-sessions/', GetNotesAPIView.as_view(), name='get-notes'),#get/
    path('allusers-watched-sessions/', AllUsersWatchedSessionsView.as_view(), name='all-watched-sessions'),#get/
    path('create-session/', CreateSessionAPIView.as_view(), name='create-session'),
    # path('rapid-transcript/', RapidTranscriptAPIView.as_view(), name='test-rapid-api')
]




