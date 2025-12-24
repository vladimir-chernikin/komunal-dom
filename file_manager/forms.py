from django import forms
from .models import UserFile


class FileUploadForm(forms.ModelForm):
    """Форма для загрузки файлов"""

    class Meta:
        model = UserFile
        fields = ['file', 'description']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Добавьте описание файла (необязательно)'
            }),
        }
        labels = {
            'file': 'Выберите файл',
            'description': 'Описание',
        }