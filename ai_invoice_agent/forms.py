from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Email Address')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")  # Explicitly define fields

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email
