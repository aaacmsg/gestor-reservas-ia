from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # Página principal
    path('calendario/<int:resource_id>/', views.calendario, name='calendario'),
    path('calendario_full/<int:resource_id>/', views.calendario_full, name='calendario_full'),
    path('api/reservas/<int:resource_id>/', views.api_reservas, name='api_reservas'),
    path('api/reservas/crear/', views.api_crear_reserva, name='api_crear_reserva'),
    path('api/disponibilidad/<int:resource_id>/', views.api_disponibilidad, name='api_disponibilidad'),
    path('cuenta/pagos/', views.mis_pagos, name='mis_pagos'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),



]
