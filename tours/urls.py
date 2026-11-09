from django.urls import path

from . import views

urlpatterns = [
    path("", views.tour_list, name="tour_list"),
    path("tours/<int:pk>/", views.tour_detail, name="tour_detail"),
    path("tours/<int:pk>/book/", views.book_tour, name="book_tour"),
    path("tours/<int:pk>/comment/", views.add_comment, name="add_comment"),
    path("my-bookings/", views.my_bookings, name="my_bookings"),
    path("register/", views.register, name="register"),
]
