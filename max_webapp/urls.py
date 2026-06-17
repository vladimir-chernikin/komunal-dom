from django.urls import path

from . import views

app_name = "max_webapp"

urlpatterns = [
    path("work-orders/", views.work_orders, name="work_orders"),
    path("work-orders/<int:work_order_id>/", views.work_order_detail, name="work_order_detail"),
    path("work-orders/<int:work_order_id>/save/", views.save_work_order, name="save_work_order"),
    path("work-orders/<int:work_order_id>/action/", views.run_work_order_action, name="run_work_order_action"),
    path("work-orders/<int:work_order_id>/photos/", views.upload_work_order_photos, name="upload_work_order_photos"),
    path("speech-to-text/", views.speech_to_text, name="speech_to_text"),
    path("microphone-diagnostics/", views.microphone_diagnostics, name="microphone_diagnostics"),
    path("voice-sessions/", views.create_voice_session, name="create_voice_session"),
    path("voice-sessions/<uuid:session_id>/", views.voice_session_status, name="voice_session_status"),
    path("voice-sessions/<uuid:session_id>/event/", views.voice_session_event, name="voice_session_event"),
    path("voice-sessions/<uuid:session_id>/recognize/", views.recognize_voice_session, name="recognize_voice_session"),
]
