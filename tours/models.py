from django.conf import settings
from django.db import models
from django.utils import timezone


class Category(models.Model):
    """Категория тура, например «Конный», «Пеший» или «Мото»."""

    name = models.CharField("Название", max_length=50, unique=True)

    class Meta:
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Профиль клиента.

    Связь «один к одному» со встроенным пользователем: у каждого
    пользователя может быть только один профиль.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        help_text="Пользователь, которому принадлежит профиль",
    )
    phone = models.CharField("Телефон", max_length=20)

    def __str__(self):
        return f"Профиль {self.user}"


class Tour(models.Model):
    """Тур.

    Связи:

    * ``categories``: многие ко многим с :model:`tours.Category`;
    * ``buyers``: многие ко многим с пользователями через :model:`tours.Booking`;
    * ``comments``: один ко многим с :model:`tours.Comment`.
    """

    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField("Цена", max_digits=8, decimal_places=2)
    categories = models.ManyToManyField(
        Category,
        related_name="tours",
        verbose_name="Категории",
        help_text="Один тур может относиться к нескольким категориям",
    )
    buyers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Booking",
        related_name="booked_tours",
        blank=True,
    )

    def __str__(self):
        return self.title


class Booking(models.Model):
    """Покупка тура на конкретные дату и время.

    Ограничение: один пользователь не может иметь две записи на одну
    и ту же дату и время (``UniqueConstraint`` по ``user``, ``date``, ``time``).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="bookings")
    date = models.DateField("Дата")
    time = models.TimeField("Время")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date", "time"],
                name="unique_booking_per_user_slot",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.tour} ({self.date} {self.time:%H:%M})"


class Comment(models.Model):
    """Комментарий пользователя к туру (один ко многим).

    Оставить комментарий может только тот, кто уже был в туре,
    см. :func:`has_attended`. Комментариев может быть сколько угодно.
    """

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    text = models.TextField("Текст")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.author}: {self.text[:30]}"


def has_attended(user, tour):
    """Проверяет, был ли пользователь в туре.

    Возвращает ``True``, если у пользователя есть запись на этот тур
    с датой раньше сегодняшней.
    """
    return Booking.objects.filter(
        user=user,
        tour=tour,
        date__lt=timezone.localdate(),
    ).exists()
