from django.shortcuts import redirect
from django.urls import reverse


class AccountLoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow requests to go through, Django admin handles its own auth
        return self.get_response(request)