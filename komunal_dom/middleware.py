from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin


class SubdomainMiddleware(MiddlewareMixin):
    """
    Middleware для обработки поддоменов
    - aspect.komunal-dom.ru → aspect_landing
    - www.komunal-dom.ru или komunal-dom.ru → landing
    """

    def process_request(self, request):
        host = request.get_host().lower()

        # Обработка поддомена aspect
        if host.startswith('aspect.'):
            from portal.views import aspect_landing
            return aspect_landing(request)

        return None
