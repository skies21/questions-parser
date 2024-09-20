from django.urls import path
from parsing import views

urlpatterns = [
    path('', views.index, name='index'),
    path('parse/', views.parse, name='parse'),
]
