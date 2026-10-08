from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("password/", views.ChangePasswordView.as_view(), name="password_change"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="user_edit"),
]