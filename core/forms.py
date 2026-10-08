from django import forms

from .models import Category, Department


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind"]

    def clean(self):
        cleaned = super().clean()
        name, kind = cleaned.get("name"), cleaned.get("kind")
        if name and kind and Category.objects.filter(name__iexact=name.strip(), kind=kind).exists():
            raise forms.ValidationError(f'An {kind} category named "{name.strip()}" already exists.')
        return cleaned


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Department.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(f'A department named "{name}" already exists.')
        return name