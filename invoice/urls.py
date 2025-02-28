from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_invoice, name='upload_invoice'),  # New upload endpoint
    path('process/', views.process_invoices, name='process_invoices'),
    path('chat/', views.chat_with_model, name='chat_with_model'),  # Add this line
    path('clear_chat_history/', views.clear_chat_history, name='clear_chat_history'),  # Add this!

]
