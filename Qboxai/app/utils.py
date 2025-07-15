from .models import QAModel

def has_exceeded_question_limit(user, session, max_total=30, max_per_video=5):
    if user.is_premium:
        return False, None  # Unlimited access

    # Total questions asked across all videos by this user
    total_questions = QAModel.objects.filter(session__user=user).count()

    # Questions asked in the current session (video)
    video_questions = QAModel.objects.filter(session=session).count()

    if total_questions >= max_total:
        return True, "Free users can ask only 30 questions in total. Please upgrade to premium."

    if video_questions >= max_per_video:
        return True, "Free users can ask only 5 questions per video. Please upgrade to premium."

    return False, None


