from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("rules", views.RuleViewSet, basename="reminder-rule")
router.register("templates", views.TemplateViewSet, basename="reminder-template")
router.register("logs", views.LogViewSet, basename="reminder-log")

urlpatterns = [
    path("channels/", views.ChannelConfigView.as_view(), name="reminder-channels"),
    path("preferences/", views.PreferencesView.as_view(), name="reminder-preferences"),
    path("preferences/verify-phone/", views.VerifyPhoneView.as_view(), name="reminder-verify-phone"),
    path("download/<str:token>/", views.download, name="reminder-download"),
    path("", include(router.urls)),
]
