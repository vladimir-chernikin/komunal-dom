import os
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserFile(models.Model):
    """Модель для хранения файлов пользователей"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    file = models.FileField(upload_to='user_files/%Y/%m/', verbose_name="Файл")
    filename = models.CharField(max_length=255, verbose_name="Имя файла")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")
    file_size = models.BigIntegerField(verbose_name="Размер файла (байты)")

    class Meta:
        verbose_name = "Файл пользователя"
        verbose_name_plural = "Файлы пользователей"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.user.username} - {self.filename}"

    def save(self, *args, **kwargs):
        if self.file:
            self.filename = os.path.basename(self.file.name)
            self.file_size = self.file.size
        super().save(*args, **kwargs)
