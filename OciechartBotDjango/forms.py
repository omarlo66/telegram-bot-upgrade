from django import forms


class LoginForm(forms.Form):
    password = forms.CharField(label='password',max_length=20)