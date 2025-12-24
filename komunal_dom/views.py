from django.shortcuts import redirect
from django.contrib.auth import logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

@require_http_methods(["GET", "POST"])
@login_required
def custom_logout(request):
    """Кастомный logout view"""
    logout(request)
    messages.info(request, 'Вы вышли из системы')
    return redirect('/')