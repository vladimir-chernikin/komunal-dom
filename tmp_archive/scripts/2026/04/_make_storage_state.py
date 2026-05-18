import json
from django.contrib.auth import get_user_model
from importlib import import_module
from django.conf import settings
User = get_user_model()
u = User.objects.filter(is_superuser=True).order_by('id').first()
SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
s = SessionStore()
s['_auth_user_id'] = str(u.pk)
s['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
s['_auth_user_hash'] = u.get_session_auth_hash()
s.save()
payload = {
  'cookies': [
    {
      'name': settings.SESSION_COOKIE_NAME,
      'value': s.session_key,
      'domain': 'komunal-dom.ru',
      'path': '/',
      'httpOnly': True,
      'secure': False
    }
  ],
  'origins': []
}
open('/tmp/codex_playwright_storage_import_fix.json', 'w', encoding='utf-8').write(json.dumps(payload))
print('/tmp/codex_playwright_storage_import_fix.json')
