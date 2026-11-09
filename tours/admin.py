from django.contrib import admin

from .models import Booking, Category, Comment, Profile, Tour


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    fields = ("title", "description", "price", "categories")
    list_display = ("title", "price")


admin.site.register([Category, Profile, Booking, Comment])
