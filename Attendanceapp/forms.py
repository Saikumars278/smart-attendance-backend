from django import forms
from .models import Department

class AddEmployeeForm(forms.Form):
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class':'form-control form-control-sm'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class':'form-control form-control-sm'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class':'form-control form-control-sm'}))
    phone = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'class':'form-control form-control-sm'}))
    department = forms.ModelChoiceField(queryset=Department.objects.all(), widget=forms.Select(attrs={'class':'form-select form-select-sm'}))
