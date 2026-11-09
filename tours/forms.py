from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import Booking, Comment, Profile


class RegisterForm(UserCreationForm):
    """Регистрация: стандартная форма Django плюс телефон (создаёт Profile)."""

    phone = forms.CharField(label="Телефон", max_length=20)

    class Meta(UserCreationForm.Meta):
        fields = ("username",)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            Profile.objects.create(user=user, phone=self.cleaned_data["phone"])
        return user


class BookingForm(forms.ModelForm):
    """Покупка тура: дата и время. Пользователь и тур передаются из view."""

    class Meta:
        model = Booking
        fields = ["date", "time"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, user=None, tour=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.tour = tour

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("Нельзя записаться на прошедшую дату.")
        return date

    def clean(self):
        cleaned = super().clean()
        date, time = cleaned.get("date"), cleaned.get("time")
        if (
            date
            and time
            and Booking.objects.filter(
                user=self.user,
                date=date,
                time=time,
            ).exists()
        ):
            raise forms.ValidationError("У вас уже есть тур на эту дату и время.")
        return cleaned

    def save(self, commit=True):
        booking = super().save(commit=False)
        booking.user = self.user
        booking.tour = self.tour
        if commit:
            booking.save()
        return booking


class CommentForm(forms.ModelForm):
    """Комментарий к туру."""

    class Meta:
        model = Comment
        fields = ["text"]
        labels = {"text": "Ваш комментарий"}
