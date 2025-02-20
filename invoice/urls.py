from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_invoice, name='upload_invoice'),  # New upload endpoint
    path('process/', views.process_invoices, name='process_invoices'),
]
