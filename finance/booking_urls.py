from django.urls import path

from . import views

urlpatterns = [
    path("", views.BookingListView.as_view(), name="booking_list"),
    path("new/", views.BookingCreateView.as_view(), name="booking_create"),
    path("<int:pk>/edit/", views.BookingUpdateView.as_view(), name="booking_edit"),
    path("<int:pk>/status/", views.BookingStatusView.as_view(), name="booking_status"),
]