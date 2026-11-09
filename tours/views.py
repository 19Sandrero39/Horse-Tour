from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BookingForm, CommentForm, RegisterForm
from .models import Category, Tour, has_attended


def tour_list(request):
    """Список туров.

    Параметр ``?category=<id>`` оставляет только туры выбранной категории.
    """
    tours = Tour.objects.prefetch_related("categories")
    category_id = request.GET.get("category")
    if category_id and category_id.isdigit():
        tours = tours.filter(categories__pk=category_id)
    return render(
        request,
        "tours/tour_list.html",
        {
            "tours": tours,
            "categories": Category.objects.all(),
        },
    )


def _render_detail(request, tour, booking_form=None, comment_form=None):
    can_comment = request.user.is_authenticated and has_attended(request.user, tour)
    return render(
        request,
        "tours/tour_detail.html",
        {
            "tour": tour,
            "comments": tour.comments.select_related("author"),
            "booking_form": BookingForm() if booking_form is None else booking_form,
            "comment_form": CommentForm() if comment_form is None else comment_form,
            "can_comment": can_comment,
        },
    )


def tour_detail(request, pk):
    """Страница тура: описание, форма покупки и комментарии."""
    tour = get_object_or_404(Tour, pk=pk)
    return _render_detail(request, tour)


@login_required
@require_POST
def book_tour(request, pk):
    """Покупка тура (только POST, только для авторизованных).

    Отклоняет прошедшие даты и вторую запись на ту же дату и время.
    """
    tour = get_object_or_404(Tour, pk=pk)
    form = BookingForm(request.POST, user=request.user, tour=tour)
    if form.is_valid():
        form.save()
        return redirect("my_bookings")
    return _render_detail(request, tour, booking_form=form)


@login_required
@require_POST
def add_comment(request, pk):
    """Добавление комментария (только POST).

    Если пользователь ещё не был в этом туре, возвращает 403.
    """
    tour = get_object_or_404(Tour, pk=pk)
    if not has_attended(request.user, tour):
        return HttpResponseForbidden(
            "Комментировать можно только туры, в которых вы уже были."
        )
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.tour = tour
        comment.author = request.user
        comment.save()
        return redirect("tour_detail", pk=pk)
    return _render_detail(request, tour, comment_form=form)


@login_required
def my_bookings(request):
    """Список туров, купленных текущим пользователем."""
    bookings = request.user.bookings.select_related("tour")
    return render(request, "tours/my_bookings.html", {"bookings": bookings})


def register(request):
    """Регистрация нового клиента с автоматическим входом."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("tour_list")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})
