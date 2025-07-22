
from django.core.cache import cache
import webvtt
import requests
import os
import tempfile
import logging
from urllib.parse import urlparse, parse_qs
from django.conf import settings
from django.core.cache import cache
from yt_dlp import YoutubeDL
from asgiref.sync import sync_to_async
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from .models import TranscriptModel, VideoModel, SessionModel, QAModel
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from django.core.cache import cache
genai.configure(api_key=settings.GEMINI_API_KEY)


# ✅ Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


genai.configure(api_key=settings.GEMINI_API_KEY)

YOUTUBE_API_KEY = settings.YOUTUBE_API_KEY

video_title_cache = {}
transcript_cache = {}
transcript_languages_cache = {}
# def get_video_title_with_cache(video_id, youtube_api_key=None):
#     cache_key = f"video_title:{video_id}"
#     title = cache.get(cache_key)
#
#     if title:
#         return title
#
#     # Step 1: Try YouTube API
#     if youtube_api_key:
#         title = fetch_video_title_via_api(video_id, youtube_api_key)
#
#     # Step 2: Fallback to yt-dlp
#     if not title:
#         title = fetch_video_title_via_ytdlp(video_id)
#
#     if title:
#         cache.set(cache_key, title, timeout=60 * 60 * 24)  # cache for 24 hours
#
#     return title
#
#
# def get_transcript_with_cache(video_id):
#     cache_key = f"transcript:{video_id}"
#     cached = cache.get(cache_key)
#
#     if cached:
#         logger.debug(f"Transcript cache hit for {video_id}")
#         return cached
#
#     try:
#         transcript = fetch_transcript_with_super_data_api(video_id)
#         if transcript:
#             full_text = " ".join([seg['text'] for seg in transcript])
#             data = {
#                 "segments": transcript,
#                 "full_text": full_text
#             }
#             cache.set(cache_key, data, timeout=86400)
#             return data
#     except Exception as e:
#         logger.error(f"Transcript fetch error for {video_id}: {e}")
#
#     return None
#
#
# def get_transcript_languages_cached(video_id):
#     cache_key = f"transcript_languages:{video_id}"
#     languages = cache.get(cache_key)
#
#     if languages:
#         return languages
#
#     languages = get_transcript_languages(video_id)
#
#     if languages:
#         cache.set(cache_key, languages, timeout=60 * 60 * 24)
#
#     return languages

def get_transcript_with_cache(video_id):
    if video_id in transcript_cache:
        return transcript_cache[video_id]
    transcript = fetch_transcript_with_super_data_api(video_id)
    if transcript:
        full_text = " ".join([seg['text'] for seg in transcript])
        transcript_cache[video_id] = {
            "segments": transcript,
            "full_text": full_text
        }
        return transcript_cache[video_id]

    return None

def get_video_title_with_cache(video_id, youtube_api_key=None):
    if video_id in video_title_cache:
        return video_title_cache[video_id]

    title = None

    # Step 1: Try YouTube API
    if youtube_api_key:
        title = fetch_video_title_via_api(video_id, youtube_api_key)

    # Step 2: Fallback to yt-dlp if API fails
    if not title:
        title = fetch_video_title_via_ytdlp(video_id)

    # Cache if success
    if title:
        video_title_cache[video_id] = title

    return title
def get_transcript_languages_cached(video_id):
    if video_id in transcript_languages_cache:
        print(f"[Local Cache Hit] Transcript languages for {video_id}")
        return transcript_languages_cache[video_id]

    print(f"[Local Cache Miss] Fetching transcript languages for {video_id}")
    languages = get_transcript_languages(video_id)

    if languages:
        transcript_languages_cache[video_id] = languages

    return languages

def extract_youtube_video_id(url):
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    if hostname is None:
        return None
    if 'youtu.be' in hostname:
        return parsed_url.path[1:]
    elif 'youtube.com' in hostname:
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        elif parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/embed/')[1]
        elif parsed_url.path.startswith('/shorts/'):
            return parsed_url.path.split('/shorts/')[1]
    return None


def get_transcript_languages(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        return [
            {
                "language_code": transcript.language_code,
                "language_name": transcript.language,
                "is_generated": transcript.is_generated
            }
            for transcript in transcript_list
        ]
    except (TranscriptsDisabled, VideoUnavailable, Exception) as e:
        logger.warning(f"Failed to list transcripts for video {video_id}: {e}")
        return []



def convert_to_seconds(hms_str):
    """Convert HH:MM:SS.mmm to seconds (float)."""
    h, m, s = hms_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)



def fetch_transcript_with_super_data_api(video_id):
    """
    Fetch transcript using Supadata API via RapidAPI.
    Falls back to logging warning if no transcript found or on error.
    Returns list of segments: [{'text': ..., 'start': ..., 'duration': ...}]
    """
    api_url = "https://youtube-transcripts.p.rapidapi.com/youtube/transcript"
    full_video_url = f"https://www.youtube.com/watch?v={video_id}"

    headers = {
        "x-rapidapi-host": "youtube-transcripts.p.rapidapi.com",
        "x-rapidapi-key": settings.RAPIDAPI_KEY,
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(api_url, headers=headers, params={"url": full_video_url})
        if response.status_code != 200:
            logger.warning(f"Supadata API error for {video_id}: {response.status_code} - {response.text}")
            return None

        data = response.json()
        if "content" not in data or not data["content"]:
            logger.warning(f"No transcript content returned for {video_id}. Full response: {data}")
            return None

        return [
            {
                'text': seg['text'],
                'start': seg['offset'] / 1000,      # Convert ms to seconds
                'duration': seg['duration'] / 1000  # Convert ms to seconds
            }
            for seg in data['content']
        ]

    except Exception as e:
        logger.warning(f"Exception while fetching transcript for {video_id}: {e}")
        return None



def fetch_video_title_via_api(video_id, youtube_api_key):
    try:
        youtube = build('youtube', 'v3', developerKey=youtube_api_key)
        response = youtube.videos().list(part="snippet", id=video_id).execute()
        items = response.get('items', [])
        if items:
            return items[0]['snippet']['title']
    except HttpError as e:
        logger.warning(f"YouTube API error for video {video_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error in YouTube API for video {video_id}: {e}")
    return None

def fetch_video_title_via_ytdlp(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    COOKIES_FILE = "/home/ubuntu/cookies.txt"  # Path to your cookies

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            # Optional: use cookies only if required
            # 'cookiefile': COOKIES_FILE,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title')

    except Exception as e:
        logger.error(f"Failed to fetch title for video {video_id}: {e}")
        return None

def get_transcript_model(video_id):
    return TranscriptModel.objects.filter(youtube_video_id=video_id).first()


def get_or_create_video(user, video_id, title, url):
    return VideoModel.objects.get_or_create(
        user=user,
        youtube_video_id=video_id,
        defaults={'video_title': title, 'video_url': url}
    )


def get_or_create_session(user, video):
    return SessionModel.objects.get_or_create(user=user, video=video)


def create_transcript(video_id, data):
    return TranscriptModel.objects.create(
        youtube_video_id=video_id,
        language='en',
        transcript_data=data["segments"],
        transcript_text=data.get("full_text", "")
    )
def create_qa(session, question, answer, time_stamp):
    return QAModel.objects.create(
        session=session,
        question=question,
        answer=answer.strip(),
        time_stamp=time_stamp
    )


def check_question_limit(user, session, max_total=30, max_per_video=5):
    if user.is_premium:
        return False, None
    total_questions = QAModel.objects.filter(session__user=user).count()
    video_questions = QAModel.objects.filter(session=session).count()
    if total_questions >= max_total:
        return True, "Free users can ask only 30 questions in total. Please upgrade to premium."
    if video_questions >= max_per_video:
        return True, "Free users can ask only 5 questions per video. Please upgrade to premium."
    return False, None

def generate_ai_response(prompt):
    model = genai.GenerativeModel('gemini-1.5-pro')
    response = model.generate_content(prompt)
    return getattr(response, "text", "").strip()





import re
import requests
from collections import defaultdict
from django.core.cache import cache
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from django.conf import settings

# Extract YouTube video ID
def extract_youtube_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

# Get video title using YouTube Data API with caching
# def get_video_title_with_cache(video_id, api_key):
#     cache_key = f"video_title_{video_id}"
#     title = cache.get(cache_key)
#     if title:
#         return title
#
#     url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={api_key}"
#     try:
#         response = requests.get(url)
#         if response.status_code == 200:
#             items = response.json().get("items")
#             if items:
#                 title = items[0]["snippet"]["title"]
#                 cache.set(cache_key, title, timeout=60 * 60)  # cache for 1 hour
#                 return title
#     except Exception:
#         pass
#
#     return None

# Get transcript from YouTube
import requests

SUPADATA_API_KEY = "sd_03adb91d08904ee735b288b4655c1d51"
SUPADATA_API_URL = "https://api.supadata.ai/v1/youtube/transcript"

def get_transcript_from_youtube(video_id):
    api_url = "https://youtube-transcripts.p.rapidapi.com/youtube/transcript"
    full_video_url = f"https://www.youtube.com/watch?v={video_id}"

    headers = {
        "x-rapidapi-host": "youtube-transcripts.p.rapidapi.com",
        "x-rapidapi-key": settings.SUPADATA_API_KEY,
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(api_url, headers=headers, params={"url": full_video_url})

        if response.status_code != 200:
            logger.warning(f"Supadata API error for {video_id}: {response.status_code} - {response.text}")
            return None

        data = response.json()

        # Check if transcript data exists
        if "transcript" not in data or not data["transcript"]:
            logger.warning(f"No transcript found in response for {video_id}. Response: {data}")
            return None

        # Return formatted transcript
        return [
            {
                "text": entry.get("text", ""),
                "offset": int(entry.get("start", 0) * 1000)
            }
            for entry in data["transcript"]
        ]

    except Exception as e:
        logger.exception(f"Exception while fetching transcript for {video_id}: {str(e)}")
        return None


# Format seconds into HH:MM:SS
def format_time(seconds):
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hrs:02}:{mins:02}:{secs:02}"

# Group transcript into 1-minute chunks
def chunk_transcript_by_minutes(transcript):
    chunks = defaultdict(list)
    for line in transcript:
        start_sec = line["offset"] // 1000
        bucket = start_sec // 60
        chunks[bucket].append(line["text"])
    return chunks

# Generate MCQs using Gemini (Google Generative AI)
import re
import google.generativeai as genai
from django.conf import settings

def generate_mcqs_from_transcript(full_transcript_text):
    """Generate 10 advanced MCQs using Gemini AI and parse them into structured data."""
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name="models/gemini-1.5-flash-latest")

    prompt = f"""
Based on the following video transcript, create exactly 10 ADVANCED multiple choice questions that test DEEP understanding of the subject matter.

CRITICAL REQUIREMENTS FOR IN-DEPTH QUESTIONS:
1. *Mathematical/Technical Depth*
2. *Conceptual Analysis*
3. *Application & Problem-Solving*
4. *Advanced Connections*
5. *Critical Thinking*
6. *Expert-Level*

QUESTION TYPES TO INCLUDE:
- Derivation, Conceptual Analysis, Problem-Solving, Comparative Analysis, Application, Mathematical Relationships, Advanced Connections

DIFFICULTY LEVELS:
- 3 questions: Graduate/Expert level
- 4 questions: Advanced undergraduate level  
- 3 questions: Intermediate level with deep reasoning

Make distractors sophisticated and plausible.

Format each question exactly as:
Question X: [question text]
A) [option A]
B) [option B]
C) [option C]
D) [option D]
Correct Answer: [Letter]
Explanation: [Explanation]
Difficulty: [Beginner/Intermediate/Advanced/Expert]

Transcript:
\"\"\"
{full_transcript_text}
\"\"\"

Generate exactly 10 MCQs now:
"""

    try:
        response = model.generate_content(prompt)
        raw_output = response.text.strip()
        return parse_mcq_output(raw_output)
    except Exception as e:
        print(f"[Gemini ERROR] Failed to generate MCQs: {e}")
        return []

import re
def parse_mcq_output(text):
    mcq_list = []
    questions = re.split(r'Question \d+:', text)[1:]

    for q_text in questions:
        try:
            question_match = re.search(r'^(.*?)(?:\nA[\)\.])', q_text.strip(), re.DOTALL)

            # Clean lines before extracting options
            cleaned_lines = []
            for line in q_text.strip().splitlines():
                if not re.match(r'^(Correct Answer|Explanation|Difficulty):', line.strip()):
                    cleaned_lines.append(line)
            cleaned_text = "\n".join(cleaned_lines)

            options_matches = re.findall(r'^[ \t]*([A-D])[\)\.] +(.+)', cleaned_text, re.MULTILINE)
            options_dict = {label: text.strip() for label, text in options_matches}

            correct = re.search(r'Correct Answer:\s*([A-D])', q_text)
            explanation = re.search(r'Explanation:\s*(.*?)(?:\n|$)', q_text, re.DOTALL)
            difficulty = re.search(r'Difficulty:\s*(\w+)', q_text)

            mcq_list.append({
                "question": question_match.group(1).strip() if question_match else "",
                "options": options_dict,
                "correct_answer": correct.group(1).strip() if correct else "",
                "explanation": explanation.group(1).strip() if explanation else "",
                "difficulty": difficulty.group(1).strip() if difficulty else "Intermediate"
            })
        except Exception as e:
            print(f"[Parse ERROR] Skipped malformed question: {e}")
            continue

    return mcq_list







def classify_question_type(question_text):
    """Classify the type of question based on its content"""
    question_lower = question_text.lower()

    if any(word in question_lower for word in ['derive', 'derivation', 'proof', 'show that']):
        return "Derivation"
    elif any(word in question_lower for word in ['why', 'explain', 'reason', 'cause']):
        return "Conceptual Analysis"
    elif any(word in question_lower for word in ['calculate', 'solve', 'find', 'determine']):
        return "Problem Solving"
    elif any(word in question_lower for word in ['compare', 'difference', 'contrast']):
        return "Comparative Analysis"
    elif any(word in question_lower for word in ['apply', 'application', 'real-world', 'scenario']):
        return "Application"
    elif any(word in question_lower for word in ['relationship', 'effect', 'impact', 'happens when']):
        return "Mathematical Relationships"
    else:
        return "Advanced Conceptual"