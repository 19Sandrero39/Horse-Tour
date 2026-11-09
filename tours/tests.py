import datetime
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Booking, Category, Comment, Profile, Tour

User = get_user_model()


class BaseTestCase(TestCase):
    """Общие данные: категории, два тура, пользователь, даты."""

    @classmethod
    def setUpTestData(cls):
        cls.horse = Category.objects.create(name="Конный")
        cls.hike = Category.objects.create(name="Пеший")
        cls.moto = Category.objects.create(name="Мото")

        cls.tour = Tour.objects.create(title="Закат в горах", price="50.00")
        cls.tour.categories.add(cls.horse)
        cls.tour2 = Tour.objects.create(title="Мото-экспедиция", price="80.00")
        cls.tour2.categories.add(cls.moto)

        cls.user = User.objects.create_user("sasha", password="pass12345")
        Profile.objects.create(user=cls.user, phone="+996700000000")

        today = timezone.localdate()
        cls.future = today + timedelta(days=7)
        cls.past = today - timedelta(days=7)

    def book(self, tour=None, date=None, time="10:00"):
        """Отправляет форму покупки тура."""
        tour = tour or self.tour
        date = date or self.future
        return self.client.post(
            reverse("book_tour", args=[tour.pk]),
            {"date": date.isoformat(), "time": time},
        )

    def attend(self, tour, user=None, hour=10):
        """Создаёт прошедшую запись (пользователь «был» в туре)."""
        return Booking.objects.create(
            user=user or self.user,
            tour=tour,
            date=self.past,
            time=datetime.time(hour, 0),
        )


class RelationsTests(BaseTestCase):
    """Проверка связей между моделями."""

    def test_one_to_one_user_has_profile(self):
        # 1 к 1: у пользователя есть профиль
        self.assertEqual(self.user.profile.phone, "+996700000000")

    def test_one_to_one_second_profile_forbidden(self):
        # 1 к 1: второй профиль для того же пользователя создать нельзя
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Profile.objects.create(user=self.user, phone="111")

    def test_one_to_many_tour_has_many_comments(self):
        # 1 ко многим: у одного тура много комментариев
        Comment.objects.create(tour=self.tour, author=self.user, text="A")
        Comment.objects.create(tour=self.tour, author=self.user, text="B")
        self.assertEqual(self.tour.comments.count(), 2)

    def test_one_to_many_user_has_many_comments(self):
        # 1 ко многим: у одного пользователя много комментариев к разным турам
        Comment.objects.create(tour=self.tour, author=self.user, text="A")
        Comment.objects.create(tour=self.tour2, author=self.user, text="B")
        self.assertEqual(self.user.comments.count(), 2)

    def test_many_to_many_tours_and_categories(self):
        # многие ко многим: у тура несколько категорий, у категории несколько туров
        self.tour.categories.add(self.hike)
        self.tour2.categories.add(self.hike)
        self.assertEqual(self.tour.categories.count(), 2)
        self.assertEqual(self.hike.tours.count(), 2)

    def test_many_to_many_users_and_tours_via_booking(self):
        # многие ко многим через Booking: пользователи и туры
        other = User.objects.create_user("anna", password="pass12345")
        self.attend(self.tour)
        self.attend(self.tour2, hour=12)
        self.attend(self.tour, user=other)
        self.assertEqual(self.user.booked_tours.count(), 2)
        self.assertEqual(self.tour.buyers.count(), 2)


class BookingRuleTests(BaseTestCase):
    """Ограничение «1 человек, 1 тур на дату и время» на уровне базы."""

    def create(self, user=None, tour=None, date=None, hour=10):
        return Booking.objects.create(
            user=user or self.user,
            tour=tour or self.tour,
            date=date or self.future,
            time=datetime.time(hour, 0),
        )

    def test_same_user_same_slot_forbidden(self):
        # Один человек не может занять один слот дважды
        self.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create(tour=self.tour2)

    def test_same_day_other_time_allowed(self):
        # Тот же день, другое время: можно
        self.create(hour=10)
        self.create(hour=14)
        self.assertEqual(Booking.objects.count(), 2)

    def test_same_time_other_day_allowed(self):
        # То же время, другой день: можно
        self.create(date=self.future)
        self.create(date=self.future + timedelta(days=1))
        self.assertEqual(Booking.objects.count(), 2)

    def test_different_users_same_slot_allowed(self):
        # Разные люди могут быть на одном туре в одно время
        other = User.objects.create_user("anna", password="pass12345")
        self.create()
        self.create(user=other)
        self.assertEqual(Booking.objects.count(), 2)


class BookingSubmissionTests(BaseTestCase):
    """Отправка формы покупки тура."""

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_redirected_to_login(self):
        # Без входа покупка невозможна, перенаправляет на логин
        self.client.logout()
        url = reverse("book_tour", args=[self.tour.pk])
        response = self.client.post(
            url, {"date": self.future.isoformat(), "time": "10:00"}
        )
        self.assertRedirects(
            response, f"{reverse('login')}?next={url}", fetch_redirect_response=False
        )
        self.assertEqual(Booking.objects.count(), 0)

    def test_get_not_allowed(self):
        # Покупка принимает только POST
        response = self.client.get(reverse("book_tour", args=[self.tour.pk]))
        self.assertEqual(response.status_code, 405)

    def test_valid_booking_created(self):
        # Верные данные: запись создана, редирект на «Мои туры»
        response = self.book()
        self.assertRedirects(response, reverse("my_bookings"))
        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.tour, self.tour)
        self.assertEqual(booking.date, self.future)

    def test_same_slot_other_tour_rejected(self):
        # Тот же день и время на другой тур: отказ, в базе одна запись
        self.book(self.tour, time="10:00")
        response = self.book(self.tour2, time="10:00")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["booking_form"].errors)
        self.assertEqual(Booking.objects.filter(user=self.user).count(), 1)

    def test_same_slot_same_tour_rejected(self):
        # Повторная покупка того же тура на то же время: отказ
        self.book(self.tour, time="10:00")
        response = self.book(self.tour, time="10:00")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)

    def test_same_day_other_time_accepted(self):
        # Тот же день, другое время: принимается
        self.book(self.tour, time="10:00")
        self.book(self.tour2, time="15:00")
        self.assertEqual(Booking.objects.filter(user=self.user).count(), 2)

    def test_past_date_rejected(self):
        # Прошедшая дата не принимается
        response = self.book(date=self.past)
        self.assertEqual(response.status_code, 200)
        self.assertIn("date", response.context["booking_form"].errors)
        self.assertEqual(Booking.objects.count(), 0)

    def test_empty_data_rejected(self):
        # Пустая форма не принимается
        response = self.client.post(reverse("book_tour", args=[self.tour.pk]), {})
        self.assertEqual(response.status_code, 200)
        self.assertIn("date", response.context["booking_form"].errors)
        self.assertIn("time", response.context["booking_form"].errors)
        self.assertEqual(Booking.objects.count(), 0)

    def test_invalid_time_rejected(self):
        # Некорректное время не принимается
        response = self.book(time="25:99")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)


class CommentSubmissionTests(BaseTestCase):
    """Отправка комментариев."""

    def setUp(self):
        self.client.force_login(self.user)

    def comment(self, tour=None, text="Отличный тур!"):
        tour = tour or self.tour
        return self.client.post(reverse("add_comment", args=[tour.pk]), {"text": text})

    def test_anonymous_redirected_to_login(self):
        # Без входа комментарий не отправить
        self.client.logout()
        response = self.comment()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comment.objects.count(), 0)

    def test_without_booking_forbidden(self):
        # Без записи на тур комментировать нельзя (403)
        response = self.comment()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Comment.objects.count(), 0)

    def test_future_booking_forbidden(self):
        # Тур ещё не состоялся: комментировать нельзя (403)
        Booking.objects.create(
            user=self.user, tour=self.tour, date=self.future, time=datetime.time(10, 0)
        )
        response = self.comment()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Comment.objects.count(), 0)

    def test_attended_tour_comment_created(self):
        # Был в туре: комментарий сохраняется, редирект на страницу тура
        self.attend(self.tour)
        response = self.comment()
        self.assertRedirects(response, reverse("tour_detail", args=[self.tour.pk]))
        comment = Comment.objects.get()
        self.assertEqual(comment.author, self.user)
        self.assertEqual(comment.tour, self.tour)

    def test_several_comments_to_same_tour(self):
        # Можно оставить несколько комментариев к одному туру
        self.attend(self.tour)
        for text in ("Первый", "Второй", "Третий"):
            self.comment(text=text)
        self.assertEqual(Comment.objects.filter(author=self.user).count(), 3)

    def test_comments_to_several_attended_tours(self):
        # Комментарии к нескольким турам, в которых был
        self.attend(self.tour, hour=10)
        self.attend(self.tour2, hour=12)
        self.comment(self.tour)
        self.comment(self.tour2)
        self.assertEqual(self.user.comments.count(), 2)

    def test_other_tour_not_attended_forbidden(self):
        # Был только в одном туре: на другой комментировать нельзя
        self.attend(self.tour)
        response = self.comment(self.tour2)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Comment.objects.count(), 0)

    def test_empty_text_rejected(self):
        # Пустой комментарий не сохраняется
        self.attend(self.tour)
        response = self.comment(text="")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["comment_form"].errors)
        self.assertEqual(Comment.objects.count(), 0)

    def test_comment_visible_on_tour_page(self):
        # Комментарий виден на странице тура
        self.attend(self.tour)
        self.comment(text="Незабываемо")
        response = self.client.get(reverse("tour_detail", args=[self.tour.pk]))
        self.assertContains(response, "Незабываемо")


class CategoryTests(BaseTestCase):
    """Категории туров: «Конный», «Пеший», «Мото»."""

    def test_list_shows_all_categories(self):
        # На странице списка видны все категории
        response = self.client.get(reverse("tour_list"))
        for name in ("Конный", "Пеший", "Мото"):
            self.assertContains(response, name)

    def test_filter_by_category(self):
        # Фильтр показывает только туры выбранной категории
        response = self.client.get(reverse("tour_list"), {"category": self.moto.pk})
        self.assertContains(response, "Мото-экспедиция")
        self.assertNotContains(response, "Закат в горах")

    def test_tour_with_two_categories_in_both_filters(self):
        # Тур с двумя категориями находится в обоих фильтрах
        self.tour.categories.add(self.hike)
        for category in (self.horse, self.hike):
            response = self.client.get(reverse("tour_list"), {"category": category.pk})
            self.assertContains(response, "Закат в горах")

    def test_invalid_category_param_does_not_break_page(self):
        # Некорректный параметр категории не ломает страницу
        response = self.client.get(reverse("tour_list"), {"category": "abc"})
        self.assertEqual(response.status_code, 200)


class AuthSubmissionTests(BaseTestCase):
    """Отправка форм регистрации, входа и выхода."""

    REGISTER_DATA = {
        "username": "newuser",
        "password1": "Str0ngPass!2026",
        "password2": "Str0ngPass!2026",
        "phone": "+996555123456",
    }

    def test_register_creates_user_and_profile(self):
        # Регистрация создаёт пользователя и профиль, выполняет вход
        response = self.client.post(reverse("register"), self.REGISTER_DATA)
        self.assertRedirects(response, reverse("tour_list"))
        user = User.objects.get(username="newuser")
        self.assertEqual(user.profile.phone, "+996555123456")
        self.assertIn("_auth_user_id", self.client.session)

    def test_register_password_mismatch_rejected(self):
        # Разные пароли: пользователь не создаётся
        data = {**self.REGISTER_DATA, "password2": "Another!Pass2026"}
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_register_duplicate_username_rejected(self):
        # Занятый логин не принимается
        data = {**self.REGISTER_DATA, "username": "sasha"}
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="sasha").count(), 1)

    def test_register_without_phone_rejected(self):
        # Без телефона регистрация не проходит
        data = {k: v for k, v in self.REGISTER_DATA.items() if k != "phone"}
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_login_valid(self):
        # Верный логин и пароль: вход выполнен
        response = self.client.post(
            reverse("login"), {"username": "sasha", "password": "pass12345"}
        )
        self.assertRedirects(response, reverse("tour_list"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_wrong_password(self):
        # Неверный пароль: вход не выполнен
        response = self.client.post(
            reverse("login"), {"username": "sasha", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_post(self):
        # Выход через POST завершает сессию
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("tour_list"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_get_not_allowed(self):
        # Выход через GET запрещён
        self.client.force_login(self.user)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)


class PagesTests(BaseTestCase):
    """Остальные страницы."""

    def test_detail_nonexistent_returns_404(self):
        # Несуществующий тур: 404
        response = self.client.get(reverse("tour_detail", args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_my_bookings_requires_login(self):
        # «Мои туры» только для вошедших
        response = self.client.get(reverse("my_bookings"))
        self.assertEqual(response.status_code, 302)

    def test_my_bookings_shows_only_own(self):
        # В «Моих турах» только свои записи
        other = User.objects.create_user("anna", password="pass12345")
        self.attend(self.tour, user=other)
        self.attend(self.tour2, user=self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_bookings"))
        self.assertContains(response, "Мото-экспедиция")
        self.assertNotContains(response, "Закат в горах")
