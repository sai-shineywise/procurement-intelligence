from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect

from .forms import RegistrationForm


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()  # Save the user
            login(request, user)  # Log the user in immediately
            messages.success(request, "Registration successful.")
            return redirect('index')  # Redirect to your home page (change 'home' as needed)
        else:
            # log error message

            messages.error(request, "Unsuccessful registration. Invalid information.")
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})
