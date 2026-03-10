"""
Context processors для портала
"""
from .admin_views import get_user_statistics, get_file_statistics, get_prompt_statistics, get_kladr_statistics


def admin_stats(request):
    """
    Добавляет статистику в контекст админки
    """
    if request.user.is_authenticated and request.user.userprofile.has_admin_access():
        return {
            'user_stats': get_user_statistics(),
            'file_stats': get_file_statistics(),
            'prompt_stats': get_prompt_statistics(),
            'kladr_stats': get_kladr_statistics(),
        }
    return {}
