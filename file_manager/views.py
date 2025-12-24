import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.core.paginator import Paginator
from .models import UserFile
from .forms import FileUploadForm
from .decorators import file_access_required, admin_access_required


@login_required
@file_access_required
def file_list(request):
    """Список файлов текущего пользователя"""
    files = UserFile.objects.filter(user=request.user).order_by('-uploaded_at')

    # Пагинация
    paginator = Paginator(files, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Статистика
    total_files = files.count()
    total_size = sum(f.file_size for f in files)

    context = {
        'page_obj': page_obj,
        'total_files': total_files,
        'total_size': total_size,
    }
    return render(request, 'file_manager/file_list.html', context)


@login_required
@file_access_required
def upload_file(request):
    """Загрузка нового файла"""
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            user_file = form.save(commit=False)
            user_file.user = request.user
            user_file.save()
            messages.success(request, f'Файл "{user_file.filename}" успешно загружен!')
            return redirect('file_manager:file_list')
    else:
        form = FileUploadForm()

    return render(request, 'file_manager/upload_file.html', {'form': form})


@login_required
@file_access_required
def download_file(request, file_id):
    """Скачивание файла"""
    user_file = get_object_or_404(UserFile, id=file_id)

    # Проверяем права доступа
    if user_file.user != request.user:
        try:
            # Проверяем, имеет ли пользователь права администратора
            if not request.user.userprofile.has_admin_access():
                raise Http404("Файл не найден")
        except:
            raise Http404("Файл не найден")

    if os.path.exists(user_file.file.path):
        with open(user_file.file.path, 'rb') as f:
            response = HttpResponse(f.read(), content_type="application/octet-stream")
            response['Content-Disposition'] = f'attachment; filename="{user_file.filename}"'
            return response
    raise Http404("Файл не найден")


@login_required
@file_access_required
def delete_file(request, file_id):
    """Удаление файла"""
    user_file = get_object_or_404(UserFile, id=file_id)

    # Проверяем права доступа
    if user_file.user != request.user:
        try:
            # Проверяем, имеет ли пользователь права администратора
            if not request.user.userprofile.has_admin_access():
                raise Http404("Файл не найден")
        except:
            raise Http404("Файл не найден")

    if request.method == 'POST':
        filename = user_file.filename
        # Удаляем файл с диска
        if os.path.exists(user_file.file.path):
            os.remove(user_file.file.path)
        # Удаляем запись из базы
        user_file.delete()
        messages.success(request, f'Файл "{filename}" успешно удален!')
        return redirect('file_manager:file_list')

    return render(request, 'file_manager/delete_file.html', {'file': user_file})


@login_required
@admin_access_required
def all_files(request):
    """Все файлы (только для администраторов)"""

    files = UserFile.objects.all().order_by('-uploaded_at')
    paginator = Paginator(files, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_files': files.count(),
    }
    return render(request, 'file_manager/all_files.html', context)
