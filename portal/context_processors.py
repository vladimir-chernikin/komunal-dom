"""
Context processors для портала
"""
from .admin_views import get_user_statistics, get_kladr_statistics


def admin_stats(request):
    """
    Добавляет статистику в контекст админки
    """
    if request.user.is_authenticated:
        try:
            if request.user.userprofile.has_admin_access():
                return {
                    'user_stats': get_user_statistics(),
                    'kladr_stats': get_kladr_statistics(),
                }
        except Exception:
            # Если у пользователя нет профиля - игнорируем
            pass
    return {}
